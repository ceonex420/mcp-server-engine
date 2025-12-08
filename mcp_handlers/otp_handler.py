"""OTP MCP Tool Handlers.

Async wrappers for OTP MCP tools with Context support.
Provides secure OTP generation and verification for agent workflows.

This module provides MCP tool decorators for OTP functionality:
- Generate and send OTP codes via email
- Verify OTP codes entered by users

═══════════════════════════════════════════════════════════════════════════════
🔐 SECURITY ENFORCEMENT
═══════════════════════════════════════════════════════════════════════════════

CRITICAL: OTP codes are security-sensitive.

✅ ALLOWED uses:
   - Email verification workflows
   - Password reset confirmation
   - Identity verification before sensitive operations
   - Multi-factor authentication flows

❌ FORBIDDEN:
   - Exposing OTP codes in logs (only masked)
   - Storing raw OTP codes (only hashes)
   - Bypassing rate limits
   - Returning OTP codes to agents (only send via email)

Each tool enforces:
- Rate limiting (cooldown between requests)
- Maximum attempts (brute-force protection)
- Automatic expiration
- Single use (replay attack prevention)

═══════════════════════════════════════════════════════════════════════════════

Author: Odiseo Team
Created: 2025-12-07
Version: 1.0.0
"""

# NOTE: Do NOT add "from __future__ import annotations" here!
# It breaks FastMCP's Context parameter detection

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from config.settings import settings
from tools.otp.generator import OTPGenerator, get_otp_generator
from tools.otp.storage import OTPStorage, get_otp_storage
from tools.otp.validator import OTPValidator, get_otp_validator
from utils.concurrency import ConcurrencyLimitExceeded, acquire_slot
from utils.email_client import send_otp_email
from utils.logger import get_logger
from utils.rate_limiter import RateLimiter
from utils.tool_registry import ToolRegistry
from utils.validation import validate_email

# Get logger for OTP handlers
logger = get_logger("mcp_handlers_otp")

# Rate limiter for OTP operations (MCP Best Practice)
# 5 OTP generations per minute per email (prevents abuse)
otp_limiter = RateLimiter(max_calls=5, period_seconds=60)

# Global mcp instance - will be injected from server.py
mcp = None

# Dynamic tool registry - tracks tools as they're registered
otp_tool_registry = ToolRegistry()


def init_otp_handlers(mcp_instance: FastMCP) -> None:
    """Initialize OTP handlers with MCP instance.

    Args:
        mcp_instance: FastMCP server instance to register tools with.
    """
    global mcp
    mcp = mcp_instance
    register_otp_tools()
    logger.info("OTP handlers initialized successfully")


def get_otp_tool_names() -> list[str]:
    """Return list of registered OTP tool names (dynamically discovered).

    Returns:
        List of OTP tool names registered in this module
    """
    return otp_tool_registry.get_tools_by_category("otp")


def register_otp_tools() -> None:
    """Register all OTP MCP tools.

    Creates MCP tool decorators for OTP functionality.
    Each tool is an async wrapper around pure business logic functions.

    Available Tools (2 total):
    ✅ generate_otp: Generate and send OTP code via email
    ✅ verify_otp: Verify OTP code entered by user
    """

    @mcp.tool()  # type: ignore[union-attr]
    async def generate_otp(
        ctx: Context,
        email: str,
        recipient_name: str,
        purpose: str = "email_verification",
    ) -> dict[str, Any]:
        """Generate a new OTP code and send it via email.

        ** SECURITY NOTICE **:
        The OTP code is NEVER returned to the agent. It is only sent via email.
        This prevents OTP leakage through agent conversations.

        ** WHEN TO USE THIS TOOL **:
        ✅ User needs to verify their email address
        ✅ User requests password reset
        ✅ User needs identity verification before sensitive operation
        ✅ Multi-factor authentication flow

        ** EXAMPLES OF VALID USE **:
        - "Send me a verification code"
        - "I need to verify my email"
        - "Start password reset process"
        - "Verify my identity"

        ** DON'T USE WHEN **:
        ❌ User just verified (check verification status first)
        ❌ Rate limit exceeded (wait for cooldown)
        ❌ Email is invalid format
        ❌ OTP feature is disabled

        ** WHAT IT DOES **:
        1. Validates email format
        2. Checks rate limiting (cooldown period)
        3. Invalidates any previous pending OTPs
        4. Generates cryptographically secure OTP code
        5. Stores hashed OTP in database with expiration
        6. Sends OTP via email service
        7. Returns confirmation (WITHOUT the code)

        ** SECURITY MEASURES **:
        - OTP is hashed (SHA-256) before storage
        - Rate limiting prevents abuse
        - Automatic expiration
        - Previous OTPs are invalidated
        - Code is sent only via email (never returned)

        ** PERFORMANCE **: ~100-200ms (includes email queueing)

        Args:
            ctx: MCP context for logging and progress reporting.
            email: Recipient email address (e.g., "user@example.com").
            recipient_name: Recipient name for email personalization.
            purpose: OTP purpose identifier.
                    Valid values: email_verification, password_reset,
                    identity_verification, login_verification.
                    Default: "email_verification"

        Returns:
            Confirmation dict (WITHOUT the OTP code):
            {
                "success": bool,
                "message": str,
                "email": str (masked),
                "expires_in_minutes": int,
                "cooldown_seconds": int (if rate limited)
            }

        Raises:
            ValueError: If email format is invalid.
            Exception: If database or email operations fail.

        Example:
            >>> result = await generate_otp(
            ...     ctx=ctx,
            ...     email="user@example.com",
            ...     recipient_name="John Doe",
            ...     purpose="email_verification"
            ... )
            >>> print(result["message"])
            # "Verification code sent to u***@example.com"
        """
        try:
            # Check if OTP is enabled
            if not settings.OTP_ENABLED:
                await ctx.warning("OTP generation attempted but OTP is disabled")
                return {
                    "success": False,
                    "error": "otp_disabled",
                    "message": "OTP verification is currently disabled.",
                }

            # Concurrency control
            try:
                async with acquire_slot():
                    await ctx.info(f"Generating OTP for email verification")
                    await ctx.report_progress(progress=0.1, total=1.0)

                    # Validate email format
                    email = email.lower().strip()
                    is_valid, validation_msg = validate_email(email)
                    if not is_valid:
                        await ctx.warning(f"Invalid email format: {validation_msg}")
                        return {
                            "success": False,
                            "error": "invalid_email",
                            "message": validation_msg,
                        }

                    await ctx.report_progress(progress=0.2, total=1.0)

                    # Get storage and check cooldown
                    storage = get_otp_storage()
                    can_generate, cooldown_remaining = await storage.check_cooldown(
                        email=email,
                        purpose=purpose,
                    )

                    if not can_generate:
                        await ctx.info(f"OTP cooldown active: {cooldown_remaining}s remaining")
                        return {
                            "success": False,
                            "error": "rate_limited",
                            "message": f"Please wait {cooldown_remaining} seconds before requesting a new code.",
                            "cooldown_seconds": cooldown_remaining,
                        }

                    await ctx.report_progress(progress=0.3, total=1.0)

                    # Rate limiting check (per-session)
                    session_key = email  # Use email as rate limit key
                    if not otp_limiter.check(session_key):
                        await ctx.warning("OTP rate limit exceeded")
                        return {
                            "success": False,
                            "error": "rate_limited",
                            "message": "Too many OTP requests. Please try again later.",
                        }

                    await ctx.report_progress(progress=0.4, total=1.0)

                    # Invalidate previous pending OTPs
                    invalidated = await storage.invalidate_previous_otps(email, purpose)
                    if invalidated > 0:
                        await ctx.debug(f"Invalidated {invalidated} previous OTPs")

                    await ctx.report_progress(progress=0.5, total=1.0)

                    # Generate new OTP
                    generator = get_otp_generator()
                    otp = generator.generate(purpose=purpose)

                    await ctx.report_progress(progress=0.6, total=1.0)

                    # Store hashed OTP in database
                    otp_id = await storage.store_otp(
                        email=email,
                        hashed_code=otp.hashed_code,
                        expires_at=otp.expires_at,
                        purpose=purpose,
                        metadata={
                            "recipient_name": recipient_name,
                            "request_context": ctx.request_id,
                        },
                    )

                    await ctx.report_progress(progress=0.8, total=1.0)

                    # Send OTP via email (fire-and-forget)
                    await send_otp_email(
                        recipient_email=email,
                        recipient_name=recipient_name,
                        otp_code=otp.code,  # Raw code sent via email only
                        expiry_minutes=settings.OTP_EXPIRY_MINUTES,
                    )

                    await ctx.report_progress(progress=1.0, total=1.0)

                    # Mask email for response
                    email_parts = email.split("@")
                    masked_email = f"{email_parts[0][:1]}***@{email_parts[1]}"

                    await ctx.info(f"OTP generated and sent: id={otp_id}, email={masked_email}")

                    return {
                        "success": True,
                        "message": f"Verification code sent to {masked_email}. Valid for {settings.OTP_EXPIRY_MINUTES} minutes.",
                        "email": masked_email,
                        "expires_in_minutes": settings.OTP_EXPIRY_MINUTES,
                        "otp_id": otp_id,
                        "purpose": purpose,
                    }

            except ConcurrencyLimitExceeded:
                await ctx.warning("Server at capacity, too many concurrent requests")
                return {
                    "success": False,
                    "error": "concurrency_limited",
                    "message": "Server busy. Please try again.",
                }

        except ValueError as e:
            await ctx.error(f"Validation error: {e!s}")
            return {
                "success": False,
                "error": "validation_error",
                "message": str(e),
            }

        except Exception as e:
            await ctx.error(f"Error generating OTP: {e!s}")
            logger.exception(f"OTP generation failed: {e}")
            return {
                "success": False,
                "error": "internal_error",
                "message": "Failed to generate verification code. Please try again.",
            }

    @mcp.tool()  # type: ignore[union-attr]
    async def verify_otp(
        ctx: Context,
        email: str,
        code: str,
        purpose: str = "email_verification",
    ) -> dict[str, Any]:
        """Verify an OTP code entered by the user.

        ** WHEN TO USE THIS TOOL **:
        ✅ User provides a verification code they received via email
        ✅ After generate_otp was called and user has the code
        ✅ Completing email verification flow
        ✅ Confirming password reset

        ** EXAMPLES OF VALID USE **:
        - "My code is 123456"
        - "The verification code I received is 789012"
        - "Verify code 456789"
        - User provides 6-digit number after OTP was sent

        ** DON'T USE WHEN **:
        ❌ No OTP was generated for this email
        ❌ User hasn't received the code yet
        ❌ User wants to request a new code (use generate_otp)

        ** WHAT IT DOES **:
        1. Retrieves pending OTP for email
        2. Checks expiration and attempt limits
        3. Increments attempt counter (fail-safe)
        4. Compares hashes using timing-safe method
        5. Marks OTP as used on success
        6. Returns verification result

        ** SECURITY MEASURES **:
        - Timing-attack resistant comparison
        - Attempt counting before comparison (fail-safe)
        - Maximum attempts enforced
        - Single use enforcement
        - Generic error messages (no information leakage)

        ** PERFORMANCE **: ~50-100ms (database operations)

        Args:
            ctx: MCP context for logging and progress reporting.
            email: Email address that received the OTP.
            code: OTP code entered by user (6 digits by default).
            purpose: OTP purpose (must match generation purpose).
                    Default: "email_verification"

        Returns:
            Verification result dict:
            {
                "success": bool,
                "status": str (success, invalid_code, expired, max_attempts, not_found),
                "message": str,
                "attempts_remaining": int (if failed)
            }

        Example:
            >>> result = await verify_otp(
            ...     ctx=ctx,
            ...     email="user@example.com",
            ...     code="123456",
            ...     purpose="email_verification"
            ... )
            >>> if result["success"]:
            ...     print("Email verified!")
            >>> else:
            ...     print(f"Failed: {result['message']}")
        """
        try:
            # Check if OTP is enabled
            if not settings.OTP_ENABLED:
                await ctx.warning("OTP verification attempted but OTP is disabled")
                return {
                    "success": False,
                    "status": "disabled",
                    "message": "OTP verification is currently disabled.",
                }

            # Concurrency control
            try:
                async with acquire_slot():
                    await ctx.info("Verifying OTP code")
                    await ctx.report_progress(progress=0.2, total=1.0)

                    # Normalize inputs
                    email = email.lower().strip()
                    code = code.strip()

                    # Basic validation
                    if not code or not code.isdigit():
                        await ctx.warning("Invalid OTP format")
                        return {
                            "success": False,
                            "status": "invalid_code",
                            "message": "Verification code must be numeric.",
                        }

                    if len(code) != settings.OTP_CODE_LENGTH:
                        await ctx.warning(f"Invalid OTP length: {len(code)}")
                        return {
                            "success": False,
                            "status": "invalid_code",
                            "message": f"Verification code must be {settings.OTP_CODE_LENGTH} digits.",
                        }

                    await ctx.report_progress(progress=0.4, total=1.0)

                    # Perform verification
                    validator = get_otp_validator()
                    result = await validator.verify(
                        email=email,
                        code=code,
                        purpose=purpose,
                    )

                    await ctx.report_progress(progress=0.9, total=1.0)

                    # Mask email for logging
                    email_parts = email.split("@")
                    masked_email = f"{email_parts[0][:1]}***@{email_parts[1]}"

                    if result.success:
                        await ctx.info(f"OTP verified successfully: email={masked_email}")
                    else:
                        await ctx.info(
                            f"OTP verification failed: email={masked_email}, "
                            f"status={result.status.value}"
                        )

                    await ctx.report_progress(progress=1.0, total=1.0)

                    return result.to_dict()

            except ConcurrencyLimitExceeded:
                await ctx.warning("Server at capacity")
                return {
                    "success": False,
                    "status": "concurrency_limited",
                    "message": "Server busy. Please try again.",
                }

        except Exception as e:
            await ctx.error(f"Error verifying OTP: {e!s}")
            logger.exception(f"OTP verification failed: {e}")
            return {
                "success": False,
                "status": "internal_error",
                "message": "Verification failed. Please try again.",
            }

    # === DYNAMIC TOOL REGISTRATION ===
    otp_tools = [
        "generate_otp",
        "verify_otp",
    ]
    otp_tool_registry.register_tools(otp_tools, "otp")

    logger.info(f"Registered {len(otp_tools)} OTP tools")
