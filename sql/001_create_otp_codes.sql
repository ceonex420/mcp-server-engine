-- ============================================================================
-- OTP Codes Table Migration
-- ============================================================================
-- Creates the otp_codes table for storing one-time password verification codes.
--
-- Security Design:
-- - OTP codes are stored as SHA-256 hashes (never plaintext)
-- - Automatic expiration via expires_at timestamp
-- - Attempt counting for brute-force protection
-- - Soft deletion (is_used flag) for audit trail
-- - JSONB metadata for extensibility
--
-- Usage:
-- Run this migration against your PostgreSQL database:
--   psql -U mcp_user -d mcpdb -f 001_create_otp_codes.sql
--
-- Or update the SCHEMA_NAME variable below to match your environment.
-- ============================================================================

-- Set the schema name (change this to match your environment)
-- Default: 'test' (matches MCP server default)
\set schema_name 'test'

-- Create schema if not exists
CREATE SCHEMA IF NOT EXISTS :schema_name;

-- Create otp_codes table
CREATE TABLE IF NOT EXISTS :schema_name.otp_codes (
    -- Primary key
    id BIGSERIAL PRIMARY KEY,

    -- Target email address (indexed for lookups)
    email VARCHAR(255) NOT NULL,

    -- SHA-256/384/512 hash of the OTP code (never store plaintext!)
    -- SHA-256 = 64 chars, SHA-384 = 96 chars, SHA-512 = 128 chars
    hashed_code VARCHAR(128) NOT NULL,

    -- Purpose/context for the OTP
    -- Examples: email_verification, password_reset, login_verification
    purpose VARCHAR(50) NOT NULL DEFAULT 'email_verification',

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    verified_at TIMESTAMPTZ,  -- NULL until successfully verified

    -- Attempt tracking (brute-force protection)
    attempts INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 3,

    -- Usage flag (soft delete - keeps for audit)
    is_used BOOLEAN NOT NULL DEFAULT FALSE,

    -- Additional context (IP, user agent, invalidation reason, etc.)
    metadata JSONB
);

-- ============================================================================
-- Indexes for Performance
-- ============================================================================

-- Primary lookup: Find pending OTPs by email and purpose
-- Used by: get_pending_otp(), check_cooldown()
CREATE INDEX IF NOT EXISTS idx_otp_codes_email_purpose
    ON :schema_name.otp_codes (email, purpose);

-- Expiration queries: Find expired OTPs for cleanup
-- Used by: cleanup_expired_otps()
CREATE INDEX IF NOT EXISTS idx_otp_codes_expires_at
    ON :schema_name.otp_codes (expires_at);

-- Pending OTPs lookup: Find valid (not used, not expired) OTPs
-- Used by: get_pending_otp()
CREATE INDEX IF NOT EXISTS idx_otp_codes_pending
    ON :schema_name.otp_codes (email, purpose, is_used, expires_at)
    WHERE is_used = FALSE;

-- Verification tracking: Find verified OTPs
-- Used by: statistics queries
CREATE INDEX IF NOT EXISTS idx_otp_codes_verified
    ON :schema_name.otp_codes (verified_at)
    WHERE verified_at IS NOT NULL;

-- ============================================================================
-- Constraints
-- ============================================================================

-- Ensure max_attempts is reasonable
ALTER TABLE :schema_name.otp_codes
    ADD CONSTRAINT chk_otp_max_attempts
    CHECK (max_attempts BETWEEN 1 AND 10);

-- Ensure attempts don't exceed max
ALTER TABLE :schema_name.otp_codes
    ADD CONSTRAINT chk_otp_attempts
    CHECK (attempts <= max_attempts);

-- Ensure expires_at is after created_at
ALTER TABLE :schema_name.otp_codes
    ADD CONSTRAINT chk_otp_expiry
    CHECK (expires_at > created_at);

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON TABLE :schema_name.otp_codes IS
    'Stores one-time password codes for email verification, password reset, etc. '
    'Codes are stored as hashes for security.';

COMMENT ON COLUMN :schema_name.otp_codes.hashed_code IS
    'SHA-256/384/512 hash of the OTP code. Never stores plaintext codes.';

COMMENT ON COLUMN :schema_name.otp_codes.purpose IS
    'OTP purpose: email_verification, password_reset, login_verification, identity_verification';

COMMENT ON COLUMN :schema_name.otp_codes.attempts IS
    'Number of verification attempts. Incremented on each verify call.';

COMMENT ON COLUMN :schema_name.otp_codes.is_used IS
    'TRUE when OTP is consumed (verified or invalidated). Prevents replay attacks.';

COMMENT ON COLUMN :schema_name.otp_codes.metadata IS
    'JSONB for additional context: recipient_name, ip_address, user_agent, invalidation_reason';

-- ============================================================================
-- Verification
-- ============================================================================

-- Verify table was created
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'test'
          AND table_name = 'otp_codes'
    ) THEN
        RAISE NOTICE 'SUCCESS: Table test.otp_codes created successfully';
    ELSE
        RAISE EXCEPTION 'FAILED: Table test.otp_codes was not created';
    END IF;
END $$;

-- Show table structure
\d :schema_name.otp_codes
