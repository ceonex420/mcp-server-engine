"""OTP Code Generator with Cryptographically Secure Randomness.

Generates secure one-time passwords using Python's secrets module,
which provides cryptographically strong random numbers suitable for
security-sensitive applications.

Security Notes:
- Uses secrets.randbelow() for CSPRNG (OS-level entropy)
- Codes are numeric only (0-9) for easy input
- Length is configurable (4-8 digits)
- Generated codes are meant to be hashed before storage

References:
- https://docs.python.org/3/library/secrets.html
- RFC 4226 (HOTP) / RFC 6238 (TOTP) for OTP best practices
- OWASP Authentication Cheat Sheet

Author: Odiseo Team
Version: 1.0.0
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from config.settings import settings
from utils.logger import get_logger

if TYPE_CHECKING:
    pass

# Module logger
logger = get_logger("mcp_otp_generator")


@dataclass(frozen=True)
class OTPCode:
    """Immutable OTP code value object.

    Contains the generated OTP code along with its metadata.
    The raw code should only be used for sending to the user;
    the hashed version should be stored in the database.

    Attributes:
        code: The raw OTP code (numeric string)
        hashed_code: SHA-256 hash of the code for secure storage
        created_at: UTC timestamp when OTP was generated
        expires_at: UTC timestamp when OTP expires
        purpose: Purpose/context for the OTP (e.g., "email_verification")
    """

    code: str
    hashed_code: str
    created_at: datetime
    expires_at: datetime
    purpose: str

    @property
    def is_expired(self) -> bool:
        """Check if OTP has expired."""
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def time_remaining_seconds(self) -> int:
        """Get seconds remaining until expiration."""
        delta = self.expires_at - datetime.now(timezone.utc)
        return max(0, int(delta.total_seconds()))


class OTPGenerator:
    """Secure OTP code generator.

    Generates cryptographically secure one-time passwords with
    configurable length, expiration, and hashing algorithm.

    Example:
        generator = OTPGenerator()
        otp = generator.generate(purpose="email_verification")
        print(f"Send this code to user: {otp.code}")
        print(f"Store this hash: {otp.hashed_code}")
    """

    def __init__(
        self,
        code_length: int | None = None,
        expiry_minutes: int | None = None,
        hash_algorithm: str | None = None,
    ) -> None:
        """Initialize OTP generator with configuration.

        Args:
            code_length: OTP length (default from settings)
            expiry_minutes: Minutes until expiration (default from settings)
            hash_algorithm: Hash algorithm for storage (default from settings)
        """
        self.code_length = code_length or settings.OTP_CODE_LENGTH
        self.expiry_minutes = expiry_minutes or settings.OTP_EXPIRY_MINUTES
        self.hash_algorithm = hash_algorithm or settings.OTP_HASH_ALGORITHM

        # Validate code length
        if not 4 <= self.code_length <= 8:
            raise ValueError(f"OTP code length must be 4-8, got {self.code_length}")

        logger.debug(
            f"OTPGenerator initialized: length={self.code_length}, "
            f"expiry={self.expiry_minutes}min, hash={self.hash_algorithm}"
        )

    def _generate_code(self) -> str:
        """Generate cryptographically secure numeric OTP code.

        Uses secrets.randbelow() which is cryptographically secure,
        unlike random.randint() which is not suitable for security.

        Returns:
            Numeric string of configured length (e.g., "123456")
        """
        # Generate each digit using CSPRNG
        # secrets.randbelow(10) returns 0-9 with uniform distribution
        digits = [str(secrets.randbelow(10)) for _ in range(self.code_length)]
        return "".join(digits)

    def _hash_code(self, code: str) -> str:
        """Hash OTP code for secure storage.

        Uses timing-attack resistant comparison later via secrets.compare_digest().
        Never store raw OTP codes in the database.

        Args:
            code: Raw OTP code to hash

        Returns:
            Hex-encoded hash of the code
        """
        # Get hash function based on configuration
        hash_func = getattr(hashlib, self.hash_algorithm)
        # Encode as bytes and hash
        return hash_func(code.encode("utf-8")).hexdigest()

    def generate(
        self,
        purpose: str | None = None,
    ) -> OTPCode:
        """Generate a new OTP code with metadata.

        Creates a cryptographically secure OTP code along with
        its hash and expiration timestamp.

        Args:
            purpose: Purpose for the OTP (default from settings)

        Returns:
            OTPCode value object with code, hash, and timestamps

        Example:
            >>> otp = generator.generate(purpose="password_reset")
            >>> send_email(user_email, code=otp.code)  # Send raw code
            >>> db.store(otp.hashed_code, otp.expires_at)  # Store hash
        """
        purpose = purpose or settings.OTP_PURPOSE_VERIFICATION
        now = datetime.now(timezone.utc)

        # Generate cryptographically secure code
        code = self._generate_code()

        # Create OTP value object
        otp = OTPCode(
            code=code,
            hashed_code=self._hash_code(code),
            created_at=now,
            expires_at=now + timedelta(minutes=self.expiry_minutes),
            purpose=purpose,
        )

        logger.info(
            f"OTP generated: purpose={purpose}, "
            f"expires_in={self.expiry_minutes}min, "
            f"length={self.code_length}"
        )

        return otp

    @staticmethod
    def hash_for_comparison(code: str, algorithm: str | None = None) -> str:
        """Hash a code for comparison (used during verification).

        Args:
            code: Raw OTP code to hash
            algorithm: Hash algorithm (default from settings)

        Returns:
            Hex-encoded hash of the code
        """
        algorithm = algorithm or settings.OTP_HASH_ALGORITHM
        hash_func = getattr(hashlib, algorithm)
        return hash_func(code.encode("utf-8")).hexdigest()


# Singleton generator instance
_generator: OTPGenerator | None = None


def get_otp_generator() -> OTPGenerator:
    """Get or create singleton OTP generator.

    Returns:
        OTPGenerator instance
    """
    global _generator
    if _generator is None:
        _generator = OTPGenerator()
    return _generator


def generate_otp_code(purpose: str | None = None) -> OTPCode:
    """Convenience function to generate OTP code.

    Args:
        purpose: Purpose for the OTP

    Returns:
        OTPCode value object
    """
    return get_otp_generator().generate(purpose=purpose)
