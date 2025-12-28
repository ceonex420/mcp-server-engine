"""OTP Database Storage with Repository Pattern.

Handles all database operations for OTP codes using async PostgreSQL.
Implements secure storage practices:
- OTP codes are stored as hashes (never plaintext)
- Automatic expiration checking
- Attempt counting for brute-force protection
- Soft deletion (marks as used, keeps for audit)

Database Table: {schema}.otp_codes
- id: BIGSERIAL PRIMARY KEY
- email: VARCHAR(255) - Target email address
- hashed_code: VARCHAR(128) - SHA-256/384/512 hash of OTP
- purpose: VARCHAR(50) - OTP purpose (email_verification, password_reset, etc.)
- created_at: TIMESTAMPTZ - Creation timestamp
- expires_at: TIMESTAMPTZ - Expiration timestamp
- verified_at: TIMESTAMPTZ - When OTP was successfully verified (NULL if pending)
- attempts: INT - Number of verification attempts
- max_attempts: INT - Maximum allowed attempts
- is_used: BOOLEAN - Whether OTP has been consumed
- metadata: JSONB - Additional context (IP, user agent, etc.)

Author: Odiseo Team
Version: 1.0.0
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from config.settings import settings
from utils.db_async import fetchall_async, fetchone_async
from utils.logger import get_logger

# Module logger
logger = get_logger("mcp_otp_storage")


@dataclass
class OTPRecord:
    """OTP database record representation.

    Maps to the otp_codes table in the database.
    """

    id: int
    email: str
    hashed_code: str
    purpose: str
    created_at: datetime
    expires_at: datetime
    verified_at: datetime | None
    attempts: int
    max_attempts: int
    is_used: bool
    metadata: dict[str, Any] | None

    @property
    def is_expired(self) -> bool:
        """Check if OTP has expired."""
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if OTP is still valid for verification."""
        return not self.is_used and not self.is_expired and self.attempts < self.max_attempts

    @property
    def attempts_remaining(self) -> int:
        """Get remaining verification attempts."""
        return max(0, self.max_attempts - self.attempts)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> OTPRecord:
        """Create OTPRecord from database row."""
        return cls(
            id=row["id"],
            email=row["email"],
            hashed_code=row["hashed_code"],
            purpose=row["purpose"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            verified_at=row.get("verified_at"),
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
            is_used=row["is_used"],
            metadata=row.get("metadata"),
        )


class OTPStorage:
    """Repository for OTP database operations.

    Provides async CRUD operations for OTP codes with
    proper security measures and audit logging.

    Example:
        storage = OTPStorage()
        otp_id = await storage.store_otp(
            email="user@example.com",
            hashed_code="abc123...",
            expires_at=datetime.now() + timedelta(minutes=10)
        )
    """

    def __init__(self, schema_name: str | None = None) -> None:
        """Initialize OTP storage.

        Args:
            schema_name: Database schema (default from settings)
        """
        self.schema = schema_name or settings.SCHEMA_NAME
        self.table = f"{self.schema}.otp_codes"
        logger.debug(f"OTPStorage initialized: table={self.table}")

    async def store_otp(
        self,
        email: str,
        hashed_code: str,
        expires_at: datetime,
        purpose: str | None = None,
        max_attempts: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Store a new OTP code in the database.

        Args:
            email: Target email address
            hashed_code: SHA hash of the OTP code
            expires_at: Expiration timestamp
            purpose: OTP purpose (default from settings)
            max_attempts: Max verification attempts (default from settings)
            metadata: Additional context (IP, user agent, etc.)

        Returns:
            ID of the created OTP record

        Raises:
            Exception: If database operation fails
        """
        purpose = purpose or settings.OTP_PURPOSE_VERIFICATION
        max_attempts = max_attempts or settings.OTP_MAX_ATTEMPTS

        sql = f"""
            INSERT INTO {self.table} (
                email, hashed_code, purpose, expires_at,
                max_attempts, metadata, created_at, attempts, is_used
            )
            VALUES ($1, $2, $3, $4, $5, $6, NOW(), 0, FALSE)
            RETURNING id
        """

        import json

        metadata_json = json.dumps(metadata) if metadata else None

        result = await fetchone_async(
            sql, email, hashed_code, purpose, expires_at, max_attempts, metadata_json
        )

        otp_id = result["id"]
        logger.info(f"OTP stored: id={otp_id}, email={email[:3]}***@***, purpose={purpose}")
        return otp_id

    async def get_otp_by_id(self, otp_id: int) -> OTPRecord | None:
        """Get OTP record by ID.

        Args:
            otp_id: OTP record ID

        Returns:
            OTPRecord if found, None otherwise
        """
        sql = f"""
            SELECT id, email, hashed_code, purpose, created_at, expires_at,
                   verified_at, attempts, max_attempts, is_used, metadata
            FROM {self.table}
            WHERE id = $1
        """

        row = await fetchone_async(sql, otp_id)
        if row:
            return OTPRecord.from_row(row)
        return None

    async def get_pending_otp(
        self,
        email: str,
        purpose: str | None = None,
    ) -> OTPRecord | None:
        """Get the latest pending (valid) OTP for an email.

        Args:
            email: Target email address
            purpose: OTP purpose filter

        Returns:
            Latest valid OTPRecord if found, None otherwise
        """
        purpose = purpose or settings.OTP_PURPOSE_VERIFICATION

        sql = f"""
            SELECT id, email, hashed_code, purpose, created_at, expires_at,
                   verified_at, attempts, max_attempts, is_used, metadata
            FROM {self.table}
            WHERE email = $1
              AND purpose = $2
              AND is_used = FALSE
              AND expires_at > NOW()
              AND attempts < max_attempts
            ORDER BY created_at DESC
            LIMIT 1
        """

        row = await fetchone_async(sql, email, purpose)
        if row:
            return OTPRecord.from_row(row)
        return None

    async def increment_attempts(self, otp_id: int) -> int:
        """Increment verification attempt counter.

        Args:
            otp_id: OTP record ID

        Returns:
            New attempt count
        """
        sql = f"""
            UPDATE {self.table}
            SET attempts = attempts + 1
            WHERE id = $1
            RETURNING attempts
        """

        result = await fetchone_async(sql, otp_id)
        new_count = result["attempts"]
        logger.debug(f"OTP attempts incremented: id={otp_id}, attempts={new_count}")
        return new_count

    async def mark_as_verified(self, otp_id: int) -> bool:
        """Mark OTP as successfully verified.

        Args:
            otp_id: OTP record ID

        Returns:
            True if updated, False if already used
        """
        sql = f"""
            UPDATE {self.table}
            SET is_used = TRUE,
                verified_at = NOW()
            WHERE id = $1
              AND is_used = FALSE
            RETURNING id
        """

        result = await fetchone_async(sql, otp_id)
        if result:
            logger.info(f"OTP verified: id={otp_id}")
            return True
        return False

    async def invalidate_otp(self, otp_id: int, reason: str = "manual") -> bool:
        """Invalidate an OTP (mark as used without verification).

        Args:
            otp_id: OTP record ID
            reason: Reason for invalidation

        Returns:
            True if updated
        """
        sql = f"""
            UPDATE {self.table}
            SET is_used = TRUE,
                metadata = COALESCE(metadata, '{{}}'::jsonb) ||
                           jsonb_build_object('invalidated_reason', $2, 'invalidated_at', NOW())
            WHERE id = $1
            RETURNING id
        """

        result = await fetchone_async(sql, otp_id, reason)
        if result:
            logger.info(f"OTP invalidated: id={otp_id}, reason={reason}")
            return True
        return False

    async def check_cooldown(
        self,
        email: str,
        purpose: str | None = None,
        cooldown_seconds: int | None = None,
    ) -> tuple[bool, int]:
        """Check if user is in cooldown period (rate limiting).

        Args:
            email: Target email address
            purpose: OTP purpose
            cooldown_seconds: Cooldown period (default from settings)

        Returns:
            Tuple of (can_generate, seconds_remaining)
            - can_generate: True if cooldown has passed
            - seconds_remaining: Seconds until cooldown ends (0 if can generate)
        """
        purpose = purpose or settings.OTP_PURPOSE_VERIFICATION
        cooldown_seconds = cooldown_seconds or settings.OTP_COOLDOWN_SECONDS

        sql = f"""
            SELECT created_at,
                   EXTRACT(EPOCH FROM (NOW() - created_at)) as seconds_ago
            FROM {self.table}
            WHERE email = $1
              AND purpose = $2
            ORDER BY created_at DESC
            LIMIT 1
        """

        row = await fetchone_async(sql, email, purpose)

        if not row:
            return True, 0

        seconds_ago = int(row["seconds_ago"])
        if seconds_ago >= cooldown_seconds:
            return True, 0

        remaining = cooldown_seconds - seconds_ago
        logger.debug(f"OTP cooldown active: email={email[:3]}***@***, remaining={remaining}s")
        return False, remaining

    async def invalidate_previous_otps(
        self,
        email: str,
        purpose: str | None = None,
    ) -> int:
        """Invalidate all previous pending OTPs for an email.

        Called before generating a new OTP to ensure only one active OTP exists.

        Args:
            email: Target email address
            purpose: OTP purpose

        Returns:
            Number of OTPs invalidated
        """
        purpose = purpose or settings.OTP_PURPOSE_VERIFICATION

        sql = f"""
            UPDATE {self.table}
            SET is_used = TRUE,
                metadata = COALESCE(metadata, '{{}}'::jsonb) ||
                           jsonb_build_object('invalidated_reason', 'superseded', 'invalidated_at', NOW())
            WHERE email = $1
              AND purpose = $2
              AND is_used = FALSE
            RETURNING id
        """

        rows = await fetchall_async(sql, email, purpose)
        count = len(rows)

        if count > 0:
            logger.info(f"Invalidated {count} previous OTPs: email={email[:3]}***@***")

        return count

    async def cleanup_expired_otps(self, days_old: int = 30) -> int:
        """Clean up old expired OTP records (maintenance task).

        Args:
            days_old: Delete records older than this many days

        Returns:
            Number of records deleted
        """
        sql = f"""
            DELETE FROM {self.table}
            WHERE created_at < NOW() - INTERVAL '{days_old} days'
              AND (is_used = TRUE OR expires_at < NOW())
            RETURNING id
        """

        rows = await fetchall_async(sql)
        count = len(rows)

        if count > 0:
            logger.info(f"Cleaned up {count} expired OTP records")

        return count

    async def get_otp_stats(self, email: str | None = None) -> dict[str, int]:
        """Get OTP statistics for monitoring.

        Args:
            email: Optional filter by email

        Returns:
            Statistics dictionary
        """
        if email:
            sql = f"""
                SELECT
                    COUNT(*) FILTER (WHERE is_used = FALSE AND expires_at > NOW()) as pending,
                    COUNT(*) FILTER (WHERE verified_at IS NOT NULL) as verified,
                    COUNT(*) FILTER (WHERE is_used = TRUE AND verified_at IS NULL) as expired_or_failed,
                    COUNT(*) as total
                FROM {self.table}
                WHERE email = $1
            """
            row = await fetchone_async(sql, email)
        else:
            sql = f"""
                SELECT
                    COUNT(*) FILTER (WHERE is_used = FALSE AND expires_at > NOW()) as pending,
                    COUNT(*) FILTER (WHERE verified_at IS NOT NULL) as verified,
                    COUNT(*) FILTER (WHERE is_used = TRUE AND verified_at IS NULL) as expired_or_failed,
                    COUNT(*) as total
                FROM {self.table}
            """
            row = await fetchone_async(sql)

        return {
            "pending": row["pending"] or 0,
            "verified": row["verified"] or 0,
            "expired_or_failed": row["expired_or_failed"] or 0,
            "total": row["total"] or 0,
        }


# Singleton storage instance
_storage: OTPStorage | None = None


def get_otp_storage() -> OTPStorage:
    """Get or create singleton OTP storage.

    Returns:
        OTPStorage instance
    """
    global _storage
    if _storage is None:
        _storage = OTPStorage()
    return _storage
