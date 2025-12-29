#!/usr/bin/env python3
"""
Migration 002: Create booking system tables and functions.

Usage:
    # Set DATABASE_URL environment variable first
    export DATABASE_URL="postgresql://user:pass@host:port/dbname"

    # Run the script
    python scripts/migrate_booking_tables.py

This migration creates:
- service_types table - Available services catalog
- business_hours table - Operating hours configuration
- Missing columns in appointments table
- is_slot_available() function - Slot availability checking
- get_available_slots() function - Helper for slot listing
- Sample data for immediate functionality
"""

import asyncio
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

# Schema name - matches production config
SCHEMA_NAME = os.getenv("SCHEMA_NAME", "test")


async def run_migration():
    """Run the booking tables migration."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)

    print(f"Connecting to database...")
    print(f"Using schema: {SCHEMA_NAME}")

    try:
        conn = await asyncpg.connect(database_url)
        print("Connected successfully!")

        # ============================================================================
        # 1. SERVICE TYPES TABLE
        # ============================================================================
        print("\n=== Creating service_types table ===")
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.service_types (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                display_name VARCHAR(255) NOT NULL,
                description TEXT,
                duration_minutes INT NOT NULL DEFAULT 60 CHECK (duration_minutes > 0 AND duration_minutes <= 480),
                price DECIMAL(10,2) CHECK (price >= 0),
                color VARCHAR(50) DEFAULT '#3B82F6',
                icon VARCHAR(100) DEFAULT 'calendar',
                active BOOLEAN DEFAULT true,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        print("  ✓ service_types table created")

        # Create indexes for service_types
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_service_types_active
            ON {SCHEMA_NAME}.service_types(active) WHERE active = true
        """)
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_service_types_name
            ON {SCHEMA_NAME}.service_types(name)
        """)
        print("  ✓ service_types indexes created")

        # ============================================================================
        # 2. BUSINESS HOURS TABLE
        # ============================================================================
        print("\n=== Creating business_hours table ===")
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.business_hours (
                id SERIAL PRIMARY KEY,
                day_of_week INT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
                open_time TIME NOT NULL,
                close_time TIME NOT NULL,
                break_start TIME,
                break_end TIME,
                active BOOLEAN DEFAULT true,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT chk_business_hours_times CHECK (close_time > open_time),
                CONSTRAINT chk_business_hours_break CHECK (
                    (break_start IS NULL AND break_end IS NULL) OR
                    (break_start IS NOT NULL AND break_end IS NOT NULL AND break_end > break_start)
                ),
                CONSTRAINT uq_business_hours_day UNIQUE (day_of_week)
            )
        """)
        print("  ✓ business_hours table created")

        # Create indexes for business_hours
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_business_hours_day
            ON {SCHEMA_NAME}.business_hours(day_of_week)
        """)
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_business_hours_active
            ON {SCHEMA_NAME}.business_hours(active) WHERE active = true
        """)
        print("  ✓ business_hours indexes created")

        # ============================================================================
        # 3. ADD MISSING COLUMNS TO APPOINTMENTS TABLE
        # ============================================================================
        print("\n=== Adding missing columns to appointments table ===")

        # Check and add google_calendar_event_id (referenced by booking handler)
        result = await conn.fetchval(f"""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = '{SCHEMA_NAME}'
                AND table_name = 'appointments'
                AND column_name = 'google_calendar_event_id'
            )
        """)
        if not result:
            await conn.execute(f"""
                ALTER TABLE {SCHEMA_NAME}.appointments
                ADD COLUMN google_calendar_event_id VARCHAR(255)
            """)
            print("  ✓ Added column: google_calendar_event_id")
        else:
            print("  - Column google_calendar_event_id already exists")

        # Check and add google_calendar_link
        result = await conn.fetchval(f"""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = '{SCHEMA_NAME}'
                AND table_name = 'appointments'
                AND column_name = 'google_calendar_link'
            )
        """)
        if not result:
            await conn.execute(f"""
                ALTER TABLE {SCHEMA_NAME}.appointments
                ADD COLUMN google_calendar_link VARCHAR(255)
            """)
            print("  ✓ Added column: google_calendar_link")
        else:
            print("  - Column google_calendar_link already exists")

        # Check and add cancellation_reason
        result = await conn.fetchval(f"""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = '{SCHEMA_NAME}'
                AND table_name = 'appointments'
                AND column_name = 'cancellation_reason'
            )
        """)
        if not result:
            await conn.execute(f"""
                ALTER TABLE {SCHEMA_NAME}.appointments
                ADD COLUMN cancellation_reason TEXT
            """)
            print("  ✓ Added column: cancellation_reason")
        else:
            print("  - Column cancellation_reason already exists")

        # Check and add cancelled_at
        result = await conn.fetchval(f"""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = '{SCHEMA_NAME}'
                AND table_name = 'appointments'
                AND column_name = 'cancelled_at'
            )
        """)
        if not result:
            await conn.execute(f"""
                ALTER TABLE {SCHEMA_NAME}.appointments
                ADD COLUMN cancelled_at TIMESTAMPTZ
            """)
            print("  ✓ Added column: cancelled_at")
        else:
            print("  - Column cancelled_at already exists")

        # Create index for cancelled appointments
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_appointments_cancelled
            ON {SCHEMA_NAME}.appointments(cancelled_at)
            WHERE cancelled_at IS NOT NULL
        """)
        print("  ✓ appointments indexes updated")

        # ============================================================================
        # 4. CREATE update_updated_at_column FUNCTION (IF NOT EXISTS)
        # ============================================================================
        print("\n=== Creating helper functions ===")

        # Create the update_updated_at_column function if it doesn't exist
        await conn.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = NOW();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """)
        print("  ✓ update_updated_at_column() function created")

        # ============================================================================
        # 5. IS_SLOT_AVAILABLE FUNCTION
        # ============================================================================
        print("\n=== Creating is_slot_available function ===")
        await conn.execute(f"""
            CREATE OR REPLACE FUNCTION {SCHEMA_NAME}.is_slot_available(
                p_date DATE,
                p_time TIME,
                p_duration_minutes INT DEFAULT 60,
                p_service_type VARCHAR DEFAULT NULL,
                p_exclude_booking_id INT DEFAULT NULL
            )
            RETURNS BOOLEAN AS $$
            DECLARE
                v_day_of_week INT;
                v_end_time TIME;
                v_business_open TIME;
                v_business_close TIME;
                v_break_start TIME;
                v_break_end TIME;
                v_has_conflict BOOLEAN;
                v_is_business_day BOOLEAN;
            BEGIN
                -- Calculate end time of requested slot
                v_end_time := p_time + (p_duration_minutes || ' minutes')::INTERVAL;

                -- Get day of week (0=Monday, 6=Sunday)
                -- PostgreSQL EXTRACT(DOW) returns 0=Sunday, so we adjust
                v_day_of_week := CASE EXTRACT(DOW FROM p_date)
                    WHEN 0 THEN 6  -- Sunday -> 6
                    ELSE EXTRACT(DOW FROM p_date)::INT - 1  -- Mon=0, Tue=1, etc.
                END;

                -- Check if it's a business day and get hours
                SELECT
                    true,
                    open_time,
                    close_time,
                    break_start,
                    break_end
                INTO
                    v_is_business_day,
                    v_business_open,
                    v_business_close,
                    v_break_start,
                    v_break_end
                FROM {SCHEMA_NAME}.business_hours
                WHERE day_of_week = v_day_of_week
                AND active = true;

                -- Not a business day
                IF NOT FOUND OR NOT v_is_business_day THEN
                    RETURN FALSE;
                END IF;

                -- Check if slot is within business hours
                IF p_time < v_business_open OR v_end_time > v_business_close THEN
                    RETURN FALSE;
                END IF;

                -- Check if slot overlaps with break time
                IF v_break_start IS NOT NULL AND v_break_end IS NOT NULL THEN
                    IF (p_time < v_break_end AND v_end_time > v_break_start) THEN
                        RETURN FALSE;
                    END IF;
                END IF;

                -- Check for conflicting appointments
                SELECT EXISTS (
                    SELECT 1
                    FROM {SCHEMA_NAME}.appointments a
                    WHERE a.booking_date = p_date
                    AND a.status IN ('confirmed', 'rescheduled')
                    AND (p_exclude_booking_id IS NULL OR a.id != p_exclude_booking_id)
                    AND (
                        -- New slot starts during existing appointment
                        (p_time >= a.booking_time AND p_time < a.booking_time + (a.duration_minutes || ' minutes')::INTERVAL)
                        OR
                        -- New slot ends during existing appointment
                        (v_end_time > a.booking_time AND v_end_time <= a.booking_time + (a.duration_minutes || ' minutes')::INTERVAL)
                        OR
                        -- New slot completely contains existing appointment
                        (p_time <= a.booking_time AND v_end_time >= a.booking_time + (a.duration_minutes || ' minutes')::INTERVAL)
                    )
                ) INTO v_has_conflict;

                -- Return TRUE if no conflict found
                RETURN NOT v_has_conflict;
            END;
            $$ LANGUAGE plpgsql STABLE
        """)
        print("  ✓ is_slot_available() function created")

        # ============================================================================
        # 6. GET_AVAILABLE_SLOTS FUNCTION
        # ============================================================================
        print("\n=== Creating get_available_slots function ===")
        await conn.execute(f"""
            CREATE OR REPLACE FUNCTION {SCHEMA_NAME}.get_available_slots(
                p_date DATE,
                p_service_type VARCHAR DEFAULT NULL,
                p_slot_interval_minutes INT DEFAULT 30
            )
            RETURNS TABLE (
                slot_time TIME,
                slot_end_time TIME,
                is_available BOOLEAN
            ) AS $$
            DECLARE
                v_day_of_week INT;
                v_business_open TIME;
                v_business_close TIME;
                v_duration_minutes INT;
                v_current_time TIME;
            BEGIN
                -- Get service duration or use default
                IF p_service_type IS NOT NULL THEN
                    SELECT duration_minutes INTO v_duration_minutes
                    FROM {SCHEMA_NAME}.service_types
                    WHERE name = p_service_type AND active = true;
                END IF;
                v_duration_minutes := COALESCE(v_duration_minutes, 60);

                -- Get day of week
                v_day_of_week := CASE EXTRACT(DOW FROM p_date)
                    WHEN 0 THEN 6
                    ELSE EXTRACT(DOW FROM p_date)::INT - 1
                END;

                -- Get business hours
                SELECT open_time, close_time
                INTO v_business_open, v_business_close
                FROM {SCHEMA_NAME}.business_hours
                WHERE day_of_week = v_day_of_week AND active = true;

                IF NOT FOUND THEN
                    RETURN;  -- Not a business day
                END IF;

                -- Generate slots
                v_current_time := v_business_open;
                WHILE v_current_time + (v_duration_minutes || ' minutes')::INTERVAL <= v_business_close LOOP
                    slot_time := v_current_time;
                    slot_end_time := v_current_time + (v_duration_minutes || ' minutes')::INTERVAL;
                    is_available := {SCHEMA_NAME}.is_slot_available(p_date, v_current_time, v_duration_minutes, p_service_type);
                    RETURN NEXT;
                    v_current_time := v_current_time + (p_slot_interval_minutes || ' minutes')::INTERVAL;
                END LOOP;

                RETURN;
            END;
            $$ LANGUAGE plpgsql STABLE
        """)
        print("  ✓ get_available_slots() function created")

        # ============================================================================
        # 7. TRIGGERS FOR updated_at
        # ============================================================================
        print("\n=== Creating triggers ===")

        # Trigger for service_types
        await conn.execute(f"""
            DROP TRIGGER IF EXISTS trigger_service_types_updated_at ON {SCHEMA_NAME}.service_types
        """)
        await conn.execute(f"""
            CREATE TRIGGER trigger_service_types_updated_at
                BEFORE UPDATE ON {SCHEMA_NAME}.service_types
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column()
        """)
        print("  ✓ service_types updated_at trigger")

        # Trigger for business_hours
        await conn.execute(f"""
            DROP TRIGGER IF EXISTS trigger_business_hours_updated_at ON {SCHEMA_NAME}.business_hours
        """)
        await conn.execute(f"""
            CREATE TRIGGER trigger_business_hours_updated_at
                BEFORE UPDATE ON {SCHEMA_NAME}.business_hours
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column()
        """)
        print("  ✓ business_hours updated_at trigger")

        # ============================================================================
        # 8. SAMPLE DATA - SERVICE TYPES
        # ============================================================================
        print("\n=== Inserting sample data: service_types ===")
        await conn.execute(f"""
            INSERT INTO {SCHEMA_NAME}.service_types (name, display_name, description, duration_minutes, price, color, icon)
            VALUES
                ('consultation', 'Consultation', 'General consultation session', 60, 100.00, '#3B82F6', 'users'),
                ('demo', 'Product Demo', 'Product demonstration and overview', 45, 0.00, '#10B981', 'presentation'),
                ('support', 'Technical Support', 'Technical support session', 30, 50.00, '#F59E0B', 'wrench'),
                ('training', 'Training Session', 'Training and onboarding session', 90, 150.00, '#8B5CF6', 'academic-cap'),
                ('followup', 'Follow-up', 'Follow-up meeting', 30, 0.00, '#EC4899', 'refresh')
            ON CONFLICT (name) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                description = EXCLUDED.description,
                duration_minutes = EXCLUDED.duration_minutes,
                price = EXCLUDED.price,
                color = EXCLUDED.color,
                icon = EXCLUDED.icon,
                updated_at = NOW()
        """)
        print("  ✓ 5 service types inserted/updated")

        # ============================================================================
        # 9. SAMPLE DATA - BUSINESS HOURS
        # ============================================================================
        print("\n=== Inserting sample data: business_hours ===")
        # Insert Mon-Sat business hours (Sunday excluded - closed day doesn't need hours)
        await conn.execute(f"""
            INSERT INTO {SCHEMA_NAME}.business_hours (day_of_week, open_time, close_time, break_start, break_end, active)
            VALUES
                (0, '09:00', '18:00', '13:00', '14:00', true),  -- Monday
                (1, '09:00', '18:00', '13:00', '14:00', true),  -- Tuesday
                (2, '09:00', '18:00', '13:00', '14:00', true),  -- Wednesday
                (3, '09:00', '18:00', '13:00', '14:00', true),  -- Thursday
                (4, '09:00', '18:00', '13:00', '14:00', true),  -- Friday
                (5, '10:00', '14:00', NULL, NULL, true)         -- Saturday (half day)
            ON CONFLICT (day_of_week) DO UPDATE SET
                open_time = EXCLUDED.open_time,
                close_time = EXCLUDED.close_time,
                break_start = EXCLUDED.break_start,
                break_end = EXCLUDED.break_end,
                active = EXCLUDED.active,
                updated_at = NOW()
        """)
        # Note: Sunday (day_of_week=6) is not in business_hours table
        # The is_slot_available function returns FALSE for days not in business_hours
        print("  ✓ 6 business hours entries inserted/updated (Mon-Sat)")

        # ============================================================================
        # 10. VERIFICATION
        # ============================================================================
        print("\n=== Verification ===")

        # Verify tables
        tables_result = await conn.fetch(f"""
            SELECT 'service_types' AS table_name, COUNT(*) AS row_count FROM {SCHEMA_NAME}.service_types
            UNION ALL
            SELECT 'business_hours', COUNT(*) FROM {SCHEMA_NAME}.business_hours
            UNION ALL
            SELECT 'appointments', COUNT(*) FROM {SCHEMA_NAME}.appointments
        """)
        print("\nTable row counts:")
        for row in tables_result:
            print(f"  {row['table_name']}: {row['row_count']} rows")

        # Verify appointments columns
        columns_result = await conn.fetch(f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = '{SCHEMA_NAME}'
            AND table_name = 'appointments'
            AND column_name IN ('google_calendar_link', 'cancellation_reason', 'cancelled_at')
            ORDER BY column_name
        """)
        print("\nAppointments new columns:")
        for row in columns_result:
            print(f"  {row['column_name']}: {row['data_type']}")

        # Verify functions
        functions_result = await conn.fetch(f"""
            SELECT routine_name, routine_type
            FROM information_schema.routines
            WHERE routine_schema = '{SCHEMA_NAME}'
            AND routine_name IN ('is_slot_available', 'get_available_slots')
        """)
        print("\nFunctions created:")
        for row in functions_result:
            print(f"  {row['routine_name']} ({row['routine_type']})")

        # Test is_slot_available function
        print("\nTesting is_slot_available function:")
        slot_available = await conn.fetchval(f"""
            SELECT {SCHEMA_NAME}.is_slot_available(
                CURRENT_DATE + 1,  -- Tomorrow
                '10:00'::TIME,     -- 10:00 AM
                60,                -- 60 minutes
                'consultation'     -- Service type
            )
        """)
        print(f"  is_slot_available(tomorrow, 10:00, 60min, consultation) = {slot_available}")

        await conn.close()
        print("\n" + "=" * 50)
        print("Migration 002_create_booking_tables completed successfully!")
        print("=" * 50)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_migration())
