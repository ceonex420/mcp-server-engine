-- ============================================================================
-- Database Initialization Script for MCP Server
-- ============================================================================
-- Creates required extensions, schema, tables, and functions for Cloud SQL.
--
-- Usage (Cloud SQL via Cloud Shell or psql):
--   gcloud sql connect demo-db --database=demodb --user=demo_user
--   \i 000_init_extensions_and_schema.sql
--
-- Required extensions:
--   - pg_trgm: Trigram similarity for typo-tolerant search
--   - unaccent: Accent removal for Unicode normalization
--   - vector (pgvector): Vector operations for semantic search
-- ============================================================================

-- Set the schema name (change this to match your environment)
\set schema_name 'test'

-- ============================================================================
-- Step 1: Create Extensions (requires superuser or cloudsqlsuperuser)
-- ============================================================================
-- Note: On Cloud SQL, extensions must be enabled by a user with cloudsqlsuperuser role

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify extensions
SELECT extname, extversion FROM pg_extension WHERE extname IN ('pg_trgm', 'unaccent', 'vector');

-- ============================================================================
-- Step 2: Create Schema
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS :schema_name;

-- ============================================================================
-- Step 3: Create normalize_text Function
-- ============================================================================
-- Converts text to lowercase and removes accents for fuzzy search
-- Created in BOTH public schema (for unqualified calls) and target schema

-- Public schema version (called without schema prefix)
CREATE OR REPLACE FUNCTION public.normalize_text(input_text TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN LOWER(unaccent(COALESCE(input_text, '')));
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Target schema version
CREATE OR REPLACE FUNCTION :schema_name.normalize_text(input_text TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN LOWER(unaccent(COALESCE(input_text, '')));
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION public.normalize_text(TEXT) IS
    'Normalizes text for fuzzy search: lowercase + unaccent';
COMMENT ON FUNCTION :schema_name.normalize_text(TEXT) IS
    'Normalizes text for fuzzy search: lowercase + unaccent';

-- ============================================================================
-- Step 4: Create Products Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS :schema_name.products (
    -- Primary key
    id SERIAL PRIMARY KEY,

    -- Product identifiers
    sku VARCHAR(50) NOT NULL UNIQUE,

    -- Product details
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    brand VARCHAR(100),
    tags TEXT[],
    color VARCHAR(50),
    size VARCHAR(50),
    price DECIMAL(10, 2),

    -- Vector embedding for semantic search (1536 dimensions for Gemini)
    embedding vector(1536),

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Step 5: Create Indexes for Products
-- ============================================================================

-- SKU lookup (unique index already created by UNIQUE constraint)

-- Category filter + fuzzy search
CREATE INDEX IF NOT EXISTS idx_products_category_trgm
    ON :schema_name.products USING GIN (category gin_trgm_ops);

-- Name fuzzy search
CREATE INDEX IF NOT EXISTS idx_products_name_trgm
    ON :schema_name.products USING GIN (name gin_trgm_ops);

-- Description fuzzy search
CREATE INDEX IF NOT EXISTS idx_products_description_trgm
    ON :schema_name.products USING GIN (description gin_trgm_ops);

-- Brand filter
CREATE INDEX IF NOT EXISTS idx_products_brand
    ON :schema_name.products (brand);

-- Vector similarity search (IVF index for large datasets)
-- Note: Only create after loading data. Lists = sqrt(row_count)
CREATE INDEX IF NOT EXISTS idx_products_embedding_ivfflat
    ON :schema_name.products USING ivfflat (embedding vector_l2_ops)
    WITH (lists = 100);

-- ============================================================================
-- Step 6: Create Appointments Table (for Booking System)
-- ============================================================================

CREATE TABLE IF NOT EXISTS :schema_name.appointments (
    -- Primary key
    id SERIAL PRIMARY KEY,

    -- Customer info
    customer_email VARCHAR(255) NOT NULL,
    customer_name VARCHAR(255) NOT NULL,
    customer_phone VARCHAR(50),

    -- Appointment details
    service_type VARCHAR(100) NOT NULL,
    booking_date DATE NOT NULL,
    booking_time TIME NOT NULL,
    duration_minutes INT NOT NULL DEFAULT 60,

    -- Status tracking
    status VARCHAR(50) NOT NULL DEFAULT 'confirmed',
    notes TEXT,

    -- External references
    calendar_event_id VARCHAR(255),

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Step 7: Create Indexes for Appointments
-- ============================================================================

-- Customer lookup
CREATE INDEX IF NOT EXISTS idx_appointments_customer_email
    ON :schema_name.appointments (customer_email);

-- Date range queries
CREATE INDEX IF NOT EXISTS idx_appointments_booking_date
    ON :schema_name.appointments (booking_date);

-- Status filter
CREATE INDEX IF NOT EXISTS idx_appointments_status
    ON :schema_name.appointments (status);

-- Composite: date + time for slot availability
CREATE INDEX IF NOT EXISTS idx_appointments_date_time
    ON :schema_name.appointments (booking_date, booking_time);

-- ============================================================================
-- Step 8: Create Update Trigger
-- ============================================================================

CREATE OR REPLACE FUNCTION :schema_name.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to products
DROP TRIGGER IF EXISTS trigger_products_updated_at ON :schema_name.products;
CREATE TRIGGER trigger_products_updated_at
    BEFORE UPDATE ON :schema_name.products
    FOR EACH ROW
    EXECUTE FUNCTION :schema_name.update_updated_at_column();

-- Apply to appointments
DROP TRIGGER IF EXISTS trigger_appointments_updated_at ON :schema_name.appointments;
CREATE TRIGGER trigger_appointments_updated_at
    BEFORE UPDATE ON :schema_name.appointments
    FOR EACH ROW
    EXECUTE FUNCTION :schema_name.update_updated_at_column();

-- ============================================================================
-- Verification
-- ============================================================================

DO $$
DECLARE
    ext_count INT;
    table_count INT;
BEGIN
    -- Check extensions
    SELECT COUNT(*) INTO ext_count
    FROM pg_extension
    WHERE extname IN ('pg_trgm', 'unaccent', 'vector');

    IF ext_count < 3 THEN
        RAISE WARNING 'Not all extensions installed. Found: % of 3', ext_count;
    ELSE
        RAISE NOTICE 'SUCCESS: All 3 extensions installed (pg_trgm, unaccent, vector)';
    END IF;

    -- Check tables
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_schema = 'test'
      AND table_name IN ('products', 'appointments');

    IF table_count < 2 THEN
        RAISE WARNING 'Not all tables created. Found: % of 2', table_count;
    ELSE
        RAISE NOTICE 'SUCCESS: All tables created (products, appointments)';
    END IF;

    -- Test normalize_text
    IF EXISTS (SELECT test.normalize_text('Café')) THEN
        RAISE NOTICE 'SUCCESS: normalize_text function works';
    END IF;
END $$;

-- Show final structure
\dt :schema_name.*
\di :schema_name.*
