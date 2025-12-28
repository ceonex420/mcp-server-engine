#!/usr/bin/env python3
"""
Initialize Cloud SQL database with required extensions and schema.

Usage:
    # Set DATABASE_URL environment variable first
    export DATABASE_URL="postgresql://user:pass@/dbname?host=/cloudsql/project:region:instance"

    # Run the script
    python scripts/init_cloud_sql.py

This script creates:
- Extensions: pg_trgm, unaccent, vector
- Schema: test
- Tables: products, appointments
- Function: normalize_text
"""

import asyncio
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg


async def init_database():
    """Initialize the Cloud SQL database."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)

    print(f"Connecting to database...")

    try:
        conn = await asyncpg.connect(database_url)
        print("Connected successfully!")

        # Step 1: Create extensions
        print("\n=== Creating Extensions ===")
        extensions = ["pg_trgm", "unaccent", "vector"]
        for ext in extensions:
            try:
                await conn.execute(f"CREATE EXTENSION IF NOT EXISTS {ext}")
                print(f"  ✓ {ext}")
            except Exception as e:
                print(f"  ✗ {ext}: {e}")

        # Step 2: Create schema
        print("\n=== Creating Schema ===")
        await conn.execute("CREATE SCHEMA IF NOT EXISTS test")
        print("  ✓ test schema")

        # Step 3: Create normalize_text function
        print("\n=== Creating Functions ===")
        await conn.execute("""
            CREATE OR REPLACE FUNCTION test.normalize_text(input_text TEXT)
            RETURNS TEXT AS $$
            BEGIN
                RETURN LOWER(unaccent(COALESCE(input_text, '')));
            END;
            $$ LANGUAGE plpgsql IMMUTABLE
        """)
        print("  ✓ normalize_text()")

        # Step 4: Create products table
        print("\n=== Creating Tables ===")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS test.products (
                id SERIAL PRIMARY KEY,
                sku VARCHAR(50) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                category VARCHAR(100),
                brand VARCHAR(100),
                tags TEXT[],
                color VARCHAR(50),
                size VARCHAR(50),
                price DECIMAL(10, 2),
                embedding vector(1536),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        print("  ✓ products table")

        # Step 5: Create appointments table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS test.appointments (
                id SERIAL PRIMARY KEY,
                customer_email VARCHAR(255) NOT NULL,
                customer_name VARCHAR(255) NOT NULL,
                customer_phone VARCHAR(50),
                service_type VARCHAR(100) NOT NULL,
                booking_date DATE NOT NULL,
                booking_time TIME NOT NULL,
                duration_minutes INT NOT NULL DEFAULT 60,
                status VARCHAR(50) NOT NULL DEFAULT 'confirmed',
                notes TEXT,
                calendar_event_id VARCHAR(255),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        print("  ✓ appointments table")

        # Step 6: Create indexes
        print("\n=== Creating Indexes ===")
        indexes = [
            ("idx_products_category_trgm", "CREATE INDEX IF NOT EXISTS idx_products_category_trgm ON test.products USING GIN (category gin_trgm_ops)"),
            ("idx_products_name_trgm", "CREATE INDEX IF NOT EXISTS idx_products_name_trgm ON test.products USING GIN (name gin_trgm_ops)"),
            ("idx_products_brand", "CREATE INDEX IF NOT EXISTS idx_products_brand ON test.products (brand)"),
            ("idx_appointments_email", "CREATE INDEX IF NOT EXISTS idx_appointments_customer_email ON test.appointments (customer_email)"),
            ("idx_appointments_date", "CREATE INDEX IF NOT EXISTS idx_appointments_booking_date ON test.appointments (booking_date)"),
        ]
        for name, sql in indexes:
            try:
                await conn.execute(sql)
                print(f"  ✓ {name}")
            except Exception as e:
                print(f"  ✗ {name}: {e}")

        # Verification
        print("\n=== Verification ===")

        # Check extensions
        exts = await conn.fetch(
            "SELECT extname FROM pg_extension WHERE extname IN ('pg_trgm', 'unaccent', 'vector')"
        )
        ext_names = [r['extname'] for r in exts]
        print(f"Extensions installed: {ext_names}")

        # Check tables
        tables = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'test'"
        )
        table_names = [r['table_name'] for r in tables]
        print(f"Tables in test schema: {table_names}")

        # Test normalize_text
        result = await conn.fetchval("SELECT test.normalize_text('Café')")
        print(f"normalize_text('Café') = '{result}'")

        await conn.close()
        print("\n✅ Database initialization complete!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(init_database())
