"""OTP Code Validator with Timing-Attack Resistance.

Validates OTP codes against stored hashes using secure comparison.
Implements defense-in-depth security measures:
- Timing-attack resistant comparison (secrets.compare_digest)
- Attempt counting (brute-force protection)
- Expiration checking
- Single-use enforcement (replay attack prevention)

Security Notes:
- Uses secrets.compare_digest() to prevent timing attacks
- Increments attempt counter BEFORE comparison (fail-safe)
- Returns generic error messages (no information leakage)

Author: Odiseo Team
Version: 1.0.0
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from enum import Enum
from typing import Any

from config.settings import settings
from tools.otp.generator import OTPGenerator
from tools.otp.storage import OTPRecord, OTPStorage, get_otp_storage
from utils.logger import get_logger

# Module logger
logger = get_logger("mcp_otp_validator")


class OTPVerificationStatus(Enum):
    """OTP verification result status codes."""

    SUCCESS = "success"  # OTP verified successfully
    INVALID_CODE = "invalid_code"  # Code doesn't match
    EXPIRED = "expired"  # OTP has expired
    ALREADY_USED = "already_used"  # OTP was already consumed
    MAX_ATTEMPTS = "max_attempts"  # Too many failed attempts
    NOT_FOUND = "not_found"  # No pending OTP for email
    DISABLED = "disabled"  # OTP feature is disabled


@dataclass
class OTPVerificationResult:
    """OTP verification result with detailed status.

    Provides structured response for verification attempts,
    suitable for both success and failure scenarios.
    """

    success: bool
    status: OTPVerificationStatus
    message: str
    otp_id: int | None = None
    attempts_remaining: int | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        result: dict[str, Any] = {
            "success": self.success,
            "status": self.status.value,
            "message": self.message,
        }
        if self.otp_id is not None:
            result["otp_id"] = self.otp_id
        if self.attempts_remaining is not None:
            result["attempts_remaining"] = self.attempts_remaining
        if self.metadata:
            result["metadata"] = self.metadata
        return result


class OTPValidator:
    """Secure OTP code validator.

    Validates OTP codes against stored hashes with
    timing-attack resistance and brute-force protection.

    Example:
        validator = OTPValidator()
        result = await validator.verify(
            email="user@example.com",
            code="123456",
            purpose="email_verification"
        )
        if result.success:
            print("Email verified!")
        else:
            print(f"Verification failed: {result.message}")
    """

    def __init__(self, storage: OTPStorage | None = None) -> None:
        """Initialize OTP validator.

        Args:
            storage: OTP storage instance (default: singleton)
        """
        self.storage = storage or get_otp_storage()
        self.hash_algorithm = settings.OTP_HASH_ALGORITHM
        logger.debug(f"OTPValidator initialized: hash={self.hash_algorithm}")

    def _secure_compare(self, code_hash: str, stored_hash: str) -> bool:
        """Compare hashes using timing-attack resistant method.

        Uses secrets.compare_digest() which takes constant time
        regardless of how many characters match.

        Args:
            code_hash: Hash of user-provided code
            stored_hash: Hash stored in database

        Returns:
            True if hashes match, False otherwise
        """
        # Both must be strings of equal length for compare_digest
        return secrets.compare_digest(code_hash, stored_hash)

    async def verify(
        self,
        email: str,
        code: str,
        purpose: str | None = None,
    ) -> OTPVerificationResult:
        """Verify an OTP code for the given email.

        Performs secure verification with:
        1. Check if OTP feature is enabled
        2. Retrieve pending OTP for email
        3. Check expiration and attempt limits
        4. Increment attempt counter (fail-safe)
        5. Compare hashes using timing-safe method
        6. Mark as used on success

        Args:
            email: Email address that received the OTP
            code: OTP code entered by user
            purpose: OTP purpose (default from settings)

        Returns:
            OTPVerificationResult with success status and details
        """
        purpose = purpose or settings.OTP_PURPOSE_VERIFICATION

        # Check if OTP is enabled
        if not settings.OTP_ENABLED:
            logger.warning("OTP verification attempted but OTP is disabled")
            return OTPVerificationResult(
                success=False,
                status=OTPVerificationStatus.DISABLED,
                message="OTP verification is disabled",
            )

        # Normalize email (lowercase, strip whitespace)
        email = email.lower().strip()

        # Get pending OTP for email
        otp_record = await self.storage.get_pending_otp(email, purpose)

        if not otp_record:
            logger.warning(f"No pending OTP found: email={email[:3]}***@***, purpose={purpose}")
            return OTPVerificationResult(
                success=False,
                status=OTPVerificationStatus.NOT_FOUND,
                message="No pending verification code found. Please request a new code.",
            )

        # Check if expired (defensive - should be filtered by query)
        if otp_record.is_expired:
            logger.info(f"OTP expired: id={otp_record.id}")
            return OTPVerificationResult(
                success=False,
                status=OTPVerificationStatus.EXPIRED,
                message="Verification code has expired. Please request a new code.",
                otp_id=otp_record.id,
            )

        # Check if already used (defensive - should be filtered by query)
        if otp_record.is_used:
            logger.warning(f"OTP already used: id={otp_record.id}")
            return OTPVerificationResult(
                success=False,
                status=OTPVerificationStatus.ALREADY_USED,
                message="This verification code has already been used.",
                otp_id=otp_record.id,
            )

        # Check attempt limit (defensive - should be filtered by query)
        if otp_record.attempts >= otp_record.max_attempts:
            logger.warning(f"OTP max attempts reached: id={otp_record.id}")
            return OTPVerificationResult(
                success=False,
                status=OTPVerificationStatus.MAX_ATTEMPTS,
                message="Too many verification attempts. Please request a new code.",
                otp_id=otp_record.id,
                attempts_remaining=0,
            )

        # IMPORTANT: Increment attempt counter BEFORE comparison
        # This is fail-safe: even if code is wrong, we track the attempt
        new_attempts = await self.storage.increment_attempts(otp_record.id)
        attempts_remaining = otp_record.max_attempts - new_attempts

        # Check if this attempt exceeded the limit
        if new_attempts >= otp_record.max_attempts:
            logger.warning(f"OTP max attempts exceeded: id={otp_record.id}")
            # Don't reveal if code was correct - just say max attempts
            return OTPVerificationResult(
                success=False,
                status=OTPVerificationStatus.MAX_ATTEMPTS,
                message="Too many verification attempts. Please request a new code.",
                otp_id=otp_record.id,
                attempts_remaining=0,
            )

        # Hash the provided code for comparison
        code_hash = OTPGenerator.hash_for_comparison(code, self.hash_algorithm)

        # Timing-safe comparison
        if not self._secure_compare(code_hash, otp_record.hashed_code):
            logger.info(
                f"OTP verification failed: id={otp_record.id}, "
                f"attempts={new_attempts}/{otp_record.max_attempts}"
            )
            return OTPVerificationResult(
                success=False,
                status=OTPVerificationStatus.INVALID_CODE,
                message=f"Invalid verification code. {attempts_remaining} attempts remaining.",
                otp_id=otp_record.id,
                attempts_remaining=attempts_remaining,
            )

        # SUCCESS - Mark OTP as verified
        await self.storage.mark_as_verified(otp_record.id)

        logger.info(
            f"OTP verified successfully: id={otp_record.id}, "
            f"email={email[:3]}***@***, purpose={purpose}"
        )

        return OTPVerificationResult(
            success=True,
            status=OTPVerificationStatus.SUCCESS,
            message="Verification successful.",
            otp_id=otp_record.id,
            metadata={"purpose": purpose, "verified_at": "now"},
        )

    async def check_otp_status(
        self,
        email: str,
        purpose: str | None = None,
    ) -> dict[str, Any]:
        """Check OTP status for an email (without verifying).

        Useful for checking if user has a pending OTP or needs a new one.

        Args:
            email: Email address
            purpose: OTP purpose

        Returns:
            Status dictionary with has_pending, expires_in, attempts_remaining
        """
        purpose = purpose or settings.OTP_PURPOSE_VERIFICATION
        email = email.lower().strip()

        otp_record = await self.storage.get_pending_otp(email, purpose)

        if not otp_record:
            return {
                "has_pending_otp": False,
                "can_request_new": True,
                "message": "No pending verification code.",
            }

        return {
            "has_pending_otp": True,
            "expires_in_seconds": otp_record.expires_at.timestamp()
            - __import__("datetime").datetime.now(__import__("datetime").timezone.utc).timestamp(),
            "attempts_remaining": otp_record.attempts_remaining,
            "can_request_new": False,
            "message": "Verification code pending.",
        }


# Singleton validator instance
_validator: OTPValidator | None = None


def get_otp_validator() -> OTPValidator:
    """Get or create singleton OTP validator.

    Returns:
        OTPValidator instance
    """
    global _validator
    if _validator is None:
        _validator = OTPValidator()
    return _validator


async def validate_otp_code(
    email: str,
    code: str,
    purpose: str | None = None,
) -> OTPVerificationResult:
    """Convenience function to validate OTP code.

    Args:
        email: Email address
        code: OTP code to verify
        purpose: OTP purpose

    Returns:
        OTPVerificationResult
    """
    return await get_otp_validator().verify(email, code, purpose)
