-- ============================================================================
-- Migration: Fix Functional Indexes for normalize_text() Queries
-- ============================================================================
-- Problem: Existing indexes on raw columns don't work with queries using
--          normalize_text(column). PostgreSQL needs functional indexes that
--          match the exact expression used in queries.
--
-- Before: WHERE similarity(normalize_text(name), ...) >= threshold
--         Index on (name) is NOT used
--
-- After:  Index on (normalize_text(name)) IS used
--
-- Usage:
--   psql "host=/cloudsql/gen-lang-client-0329024102:us-central1:demo-db \
--         dbname=demo user=postgres" \
--         -v schema_name=test \
--         -f sql/003_fix_search_indexes.sql
-- ============================================================================

-- Set the schema name (change this to match your environment)
\set schema_name 'test'

-- ============================================================================
-- Step 1: Drop Old Indexes (non-functional versions)
-- ============================================================================
-- These indexes are not used by queries that call normalize_text()

DROP INDEX IF EXISTS :schema_name.idx_products_name_trgm;
DROP INDEX IF EXISTS :schema_name.idx_products_description_trgm;
DROP INDEX IF EXISTS :schema_name.idx_products_category_trgm;
DROP INDEX IF EXISTS :schema_name.idx_products_brand;

-- ============================================================================
-- Step 2: Create Functional Indexes for normalize_text() Queries
-- ============================================================================
-- These indexes match the expressions used in fuzzy_search_smart queries

-- Name: functional index matching normalize_text(name)
CREATE INDEX IF NOT EXISTS idx_products_name_norm_trgm
    ON :schema_name.products USING GIN (normalize_text(name) gin_trgm_ops);

-- Description: functional index matching normalize_text(description)
CREATE INDEX IF NOT EXISTS idx_products_description_norm_trgm
    ON :schema_name.products USING GIN (normalize_text(description) gin_trgm_ops);

-- Category: functional index matching normalize_text(category)
CREATE INDEX IF NOT EXISTS idx_products_category_norm_trgm
    ON :schema_name.products USING GIN (normalize_text(category) gin_trgm_ops);

-- Brand: GIN trigram for word_similarity queries (was B-tree, needs trigram)
CREATE INDEX IF NOT EXISTS idx_products_brand_norm_trgm
    ON :schema_name.products USING GIN (normalize_text(brand) gin_trgm_ops);

-- Tags: functional index for array field used in search
-- NOTE: array_to_string is STABLE, not IMMUTABLE, so we need a wrapper function
CREATE OR REPLACE FUNCTION :schema_name.immutable_array_to_string(arr TEXT[], sep TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN array_to_string(arr, sep);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE INDEX IF NOT EXISTS idx_products_tags_norm_trgm
    ON :schema_name.products USING GIN (normalize_text(:schema_name.immutable_array_to_string(tags, ' ')) gin_trgm_ops);

-- ============================================================================
-- Step 3: Update Table Statistics
-- ============================================================================
-- Critical for query planner to use new indexes correctly

ANALYZE :schema_name.products;

-- ============================================================================
-- Verification
-- ============================================================================

DO $$
DECLARE
    idx_count INT;
    idx_names TEXT;
BEGIN
    -- Check new indexes exist
    SELECT COUNT(*), string_agg(indexname, ', ')
    INTO idx_count, idx_names
    FROM pg_indexes
    WHERE schemaname = 'test'
      AND tablename = 'products'
      AND indexname LIKE '%_norm_trgm';

    IF idx_count >= 5 THEN
        RAISE NOTICE 'SUCCESS: All 5 functional indexes created';
        RAISE NOTICE 'Indexes: %', idx_names;
    ELSE
        RAISE WARNING 'Expected 5 indexes, found: % (%)', idx_count, idx_names;
    END IF;
END $$;

-- Show all indexes on products table
\echo '\n=== Current indexes on products table ==='
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'test'
  AND tablename = 'products'
ORDER BY indexname;
