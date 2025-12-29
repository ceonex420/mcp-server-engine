-- ============================================================================
-- Migration: 002_create_booking_tables.sql
-- Description: Create missing booking system tables and functions
-- Author: Odiseo Team
-- Date: 2025-12-28
--
-- This migration adds:
-- 1. service_types table - Available services catalog
-- 2. business_hours table - Operating hours configuration
-- 3. Missing columns in appointments table
-- 4. is_slot_available() function - Slot availability checking
-- 5. Sample data for immediate functionality
-- ============================================================================

-- Use dynamic schema from psql variable or default to 'test'
\set schema_name :SCHEMA_NAME
SELECT COALESCE(:'schema_name', 'test') AS schema_name \gset

\echo 'Using schema:' :schema_name

-- ============================================================================
-- 1. SERVICE TYPES TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS :schema_name.service_types (
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
);

-- Add trigger for updated_at
DROP TRIGGER IF EXISTS trigger_service_types_updated_at ON :schema_name.service_types;
CREATE TRIGGER trigger_service_types_updated_at
    BEFORE UPDATE ON :schema_name.service_types
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Indexes
CREATE INDEX IF NOT EXISTS idx_service_types_active
    ON :schema_name.service_types(active) WHERE active = true;
CREATE INDEX IF NOT EXISTS idx_service_types_name
    ON :schema_name.service_types(name);

COMMENT ON TABLE :schema_name.service_types IS 'Catalog of available services for booking';
COMMENT ON COLUMN :schema_name.service_types.name IS 'Unique service identifier (e.g., consultation, demo)';
COMMENT ON COLUMN :schema_name.service_types.duration_minutes IS 'Service duration in minutes (max 8 hours)';
COMMENT ON COLUMN :schema_name.service_types.color IS 'Hex color for calendar display';

\echo 'Created table: service_types'

-- ============================================================================
-- 2. BUSINESS HOURS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS :schema_name.business_hours (
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
);

-- Add trigger for updated_at
DROP TRIGGER IF EXISTS trigger_business_hours_updated_at ON :schema_name.business_hours;
CREATE TRIGGER trigger_business_hours_updated_at
    BEFORE UPDATE ON :schema_name.business_hours
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Indexes
CREATE INDEX IF NOT EXISTS idx_business_hours_day
    ON :schema_name.business_hours(day_of_week);
CREATE INDEX IF NOT EXISTS idx_business_hours_active
    ON :schema_name.business_hours(active) WHERE active = true;

COMMENT ON TABLE :schema_name.business_hours IS 'Business operating hours by day of week';
COMMENT ON COLUMN :schema_name.business_hours.day_of_week IS '0=Monday, 1=Tuesday, ..., 6=Sunday';
COMMENT ON COLUMN :schema_name.business_hours.break_start IS 'Optional lunch/break start time';

\echo 'Created table: business_hours'

-- ============================================================================
-- 3. ADD MISSING COLUMNS TO APPOINTMENTS TABLE
-- ============================================================================

-- Add google_calendar_event_id column if not exists (required by booking handler)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = :'schema_name'
        AND table_name = 'appointments'
        AND column_name = 'google_calendar_event_id'
    ) THEN
        ALTER TABLE :schema_name.appointments
        ADD COLUMN google_calendar_event_id VARCHAR(255);
        RAISE NOTICE 'Added column: google_calendar_event_id';
    ELSE
        RAISE NOTICE 'Column google_calendar_event_id already exists';
    END IF;
END $$;

-- Add google_calendar_link column if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = :'schema_name'
        AND table_name = 'appointments'
        AND column_name = 'google_calendar_link'
    ) THEN
        ALTER TABLE :schema_name.appointments
        ADD COLUMN google_calendar_link VARCHAR(255);
        RAISE NOTICE 'Added column: google_calendar_link';
    ELSE
        RAISE NOTICE 'Column google_calendar_link already exists';
    END IF;
END $$;

-- Add cancellation_reason column if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = :'schema_name'
        AND table_name = 'appointments'
        AND column_name = 'cancellation_reason'
    ) THEN
        ALTER TABLE :schema_name.appointments
        ADD COLUMN cancellation_reason TEXT;
        RAISE NOTICE 'Added column: cancellation_reason';
    ELSE
        RAISE NOTICE 'Column cancellation_reason already exists';
    END IF;
END $$;

-- Add cancelled_at column if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = :'schema_name'
        AND table_name = 'appointments'
        AND column_name = 'cancelled_at'
    ) THEN
        ALTER TABLE :schema_name.appointments
        ADD COLUMN cancelled_at TIMESTAMPTZ;
        RAISE NOTICE 'Added column: cancelled_at';
    ELSE
        RAISE NOTICE 'Column cancelled_at already exists';
    END IF;
END $$;

-- Add index for cancelled appointments
CREATE INDEX IF NOT EXISTS idx_appointments_cancelled
    ON :schema_name.appointments(cancelled_at)
    WHERE cancelled_at IS NOT NULL;

\echo 'Updated table: appointments (added missing columns)'

-- ============================================================================
-- 4. IS_SLOT_AVAILABLE FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION :schema_name.is_slot_available(
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
    FROM :schema_name.business_hours
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
        FROM :schema_name.appointments a
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
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION :schema_name.is_slot_available IS
'Check if a time slot is available for booking.
Parameters:
  p_date: Date to check
  p_time: Start time to check
  p_duration_minutes: Duration of appointment (default 60)
  p_service_type: Service type (optional, for future use)
  p_exclude_booking_id: Booking ID to exclude (for rescheduling)
Returns: TRUE if slot is available, FALSE otherwise';

\echo 'Created function: is_slot_available()'

-- ============================================================================
-- 5. GET_AVAILABLE_SLOTS FUNCTION (Helper)
-- ============================================================================

CREATE OR REPLACE FUNCTION :schema_name.get_available_slots(
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
        FROM :schema_name.service_types
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
    FROM :schema_name.business_hours
    WHERE day_of_week = v_day_of_week AND active = true;

    IF NOT FOUND THEN
        RETURN;  -- Not a business day
    END IF;

    -- Generate slots
    v_current_time := v_business_open;
    WHILE v_current_time + (v_duration_minutes || ' minutes')::INTERVAL <= v_business_close LOOP
        slot_time := v_current_time;
        slot_end_time := v_current_time + (v_duration_minutes || ' minutes')::INTERVAL;
        is_available := :schema_name.is_slot_available(p_date, v_current_time, v_duration_minutes, p_service_type);
        RETURN NEXT;
        v_current_time := v_current_time + (p_slot_interval_minutes || ' minutes')::INTERVAL;
    END LOOP;

    RETURN;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION :schema_name.get_available_slots IS
'Get all time slots for a date with availability status';

\echo 'Created function: get_available_slots()'

-- ============================================================================
-- 6. SAMPLE DATA - SERVICE TYPES
-- ============================================================================

INSERT INTO :schema_name.service_types (name, display_name, description, duration_minutes, price, color, icon)
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
    updated_at = NOW();

\echo 'Inserted sample data: service_types (5 services)'

-- ============================================================================
-- 7. SAMPLE DATA - BUSINESS HOURS
-- ============================================================================

-- Monday to Friday: 9:00 AM - 6:00 PM with lunch break 1:00 PM - 2:00 PM
-- Saturday: 10:00 AM - 2:00 PM (half day)
-- Sunday: Not inserted - is_slot_available() returns FALSE for days not in table
INSERT INTO :schema_name.business_hours (day_of_week, open_time, close_time, break_start, break_end, active)
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
    updated_at = NOW();

\echo 'Inserted sample data: business_hours (Mon-Sat)'

-- ============================================================================
-- 8. VERIFICATION
-- ============================================================================

\echo ''
\echo '============================================'
\echo 'Migration 002 Complete - Verification'
\echo '============================================'

-- Verify tables
SELECT 'service_types' AS table_name, COUNT(*) AS row_count FROM :schema_name.service_types
UNION ALL
SELECT 'business_hours', COUNT(*) FROM :schema_name.business_hours
UNION ALL
SELECT 'appointments', COUNT(*) FROM :schema_name.appointments;

-- Verify appointments columns
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = :'schema_name'
AND table_name = 'appointments'
AND column_name IN ('google_calendar_event_id', 'google_calendar_link', 'cancellation_reason', 'cancelled_at')
ORDER BY column_name;

-- Verify functions
SELECT routine_name, routine_type
FROM information_schema.routines
WHERE routine_schema = :'schema_name'
AND routine_name IN ('is_slot_available', 'get_available_slots');

-- Test is_slot_available function
\echo ''
\echo 'Testing is_slot_available function:'
SELECT :schema_name.is_slot_available(
    CURRENT_DATE + 1,  -- Tomorrow
    '10:00'::TIME,     -- 10:00 AM
    60,                -- 60 minutes
    'consultation'     -- Service type
) AS slot_available;

\echo ''
\echo 'Migration 002_create_booking_tables.sql completed successfully!'
