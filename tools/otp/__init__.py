"""OTP (One-Time Password) Tools Module.

Provides secure OTP generation and verification functionality for MCP server.
Uses cryptographically secure random number generation (secrets module).

Design Patterns:
- Repository Pattern: OTPStorage handles all database operations
- Strategy Pattern: Configurable hash algorithms
- Factory Pattern: OTPGenerator creates OTP codes

Security Best Practices:
- Cryptographically secure random generation (secrets module)
- OTP codes are hashed before storage (never stored in plaintext)
- Time-based expiration
- Rate limiting (cooldown between requests)
- Maximum attempts limit (brute-force protection)
- Replay attack prevention (single use)

Author: Odiseo Team
Version: 1.0.0
"""

from tools.otp.generator import OTPGenerator, generate_otp_code
from tools.otp.storage import OTPStorage, get_otp_storage
from tools.otp.validator import OTPValidator, validate_otp_code

__all__ = [
    # Generator
    "OTPGenerator",
    "generate_otp_code",
    # Storage
    "OTPStorage",
    "get_otp_storage",
    # Validator
    "OTPValidator",
    "validate_otp_code",
]
