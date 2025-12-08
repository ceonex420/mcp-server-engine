"""HTTP Email Service Client with Circuit Breaker Pattern.

Provides an async HTTP client for integrating with the email microservice.
Implements fire-and-forget semantics with graceful degradation.

Design Patterns:
- Circuit Breaker: Prevents cascading failures when email service is down
- Retry with Exponential Backoff: Handles transient network errors
- Fire-and-Forget: Non-blocking email sending (booking never fails due to email)

Author: Odiseo Team
Version: 1.0.0
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

from config.settings import settings
from utils.logger import get_logger

# Module logger
logger = get_logger("mcp_email_client")

# Keep reference to background tasks to prevent garbage collection
_background_tasks: set[asyncio.Task[Any]] = set()


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests allowed
    OPEN = "open"  # Failures exceeded threshold, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreaker:
    """Circuit breaker implementation for email service resilience.

    Prevents overwhelming a failing service and allows graceful recovery.
    Thread-safe implementation using atomic operations.

    Attributes:
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Seconds to wait before allowing retry
        failure_count: Current consecutive failure count
        last_failure_time: Timestamp of last failure
        state: Current circuit state
    """

    failure_threshold: int = field(
        default_factory=lambda: settings.EMAIL_SERVICE_CIRCUIT_BREAKER_THRESHOLD
    )
    recovery_timeout: int = field(
        default_factory=lambda: settings.EMAIL_SERVICE_CIRCUIT_BREAKER_TIMEOUT_SECONDS
    )
    failure_count: int = field(default=0, init=False)
    last_failure_time: float = field(default=0.0, init=False)
    state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    async def record_success(self) -> None:
        """Record a successful request, reset failure count."""
        async with self._lock:
            self.failure_count = 0
            if self.state == CircuitState.HALF_OPEN:
                logger.info("Circuit breaker: HALF_OPEN → CLOSED (service recovered)")
                self.state = CircuitState.CLOSED

    async def record_failure(self) -> None:
        """Record a failed request, potentially open circuit."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                if self.state != CircuitState.OPEN:
                    logger.warning(
                        f"Circuit breaker: OPENED after {self.failure_count} failures. "
                        f"Will retry in {self.recovery_timeout}s"
                    )
                self.state = CircuitState.OPEN

    async def can_execute(self) -> bool:
        """Check if request should be allowed through circuit breaker.

        Returns:
            bool: True if request can proceed, False if blocked
        """
        async with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                elapsed = time.time() - self.last_failure_time
                if elapsed >= self.recovery_timeout:
                    logger.info("Circuit breaker: OPEN → HALF_OPEN (testing recovery)")
                    self.state = CircuitState.HALF_OPEN
                    return True
                return False

            # HALF_OPEN: allow one request through
            return True


@dataclass
class EmailRequest:
    """Email request data structure.

    Maps to the email service API schema.
    """

    to: list[str]
    subject: str
    body: str
    template_id: str | None = None
    template_vars: dict[str, Any] | None = None
    cc: list[str] | None = None
    bcc: list[str] | None = None
    metadata: dict[str, Any] | None = None
    client_message_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to API request dictionary."""
        data: dict[str, Any] = {
            "to": self.to,
            "subject": self.subject,
            "body": self.body,
        }

        if self.template_id:
            data["template_id"] = self.template_id
        if self.template_vars:
            data["template_vars"] = self.template_vars
        if self.cc:
            data["cc"] = self.cc
        if self.bcc:
            data["bcc"] = self.bcc
        if self.metadata:
            data["metadata"] = self.metadata
        if self.client_message_id:
            data["client_message_id"] = self.client_message_id

        return data


@dataclass
class EmailResponse:
    """Email service response data structure."""

    success: bool
    message_id: str | None = None
    error: str | None = None
    queued: bool = False


class EmailServiceClient:
    """Async HTTP client for email service with resilience patterns.

    Features:
    - Fire-and-forget semantics (non-blocking)
    - Circuit breaker for fault tolerance
    - Retry with exponential backoff
    - Configurable timeouts
    - Graceful degradation

    Example:
        client = EmailServiceClient()
        response = await client.send_email(
            to=["user@example.com"],
            subject="Booking Confirmation",
            body="<h1>Your booking is confirmed</h1>",
            template_id="booking_created"
        )
    """

    def __init__(self) -> None:
        """Initialize email service client with configuration."""
        self.enabled = settings.EMAIL_SERVICE_ENABLED
        self.base_url = settings.EMAIL_SERVICE_BASE_URL.rstrip("/")
        self.api_key = settings.EMAIL_SERVICE_API_KEY
        self.timeout = settings.EMAIL_SERVICE_TIMEOUT_SECONDS
        self.max_retries = settings.EMAIL_SERVICE_MAX_RETRIES
        self.retry_delay = settings.EMAIL_SERVICE_RETRY_DELAY_SECONDS
        self.circuit_breaker = CircuitBreaker()

        if self.enabled:
            logger.info(
                f"EmailServiceClient initialized: base_url={self.base_url}, "
                f"timeout={self.timeout}s, max_retries={self.max_retries}"
            )
        else:
            logger.info("EmailServiceClient disabled via configuration")

    def _get_headers(self) -> dict[str, str]:
        """Build request headers with optional authentication."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def _execute_with_retry(
        self,
        request: EmailRequest,
    ) -> EmailResponse:
        """Execute HTTP request with retry logic and circuit breaker.

        Args:
            request: Email request data

        Returns:
            EmailResponse with success status
        """
        # Check circuit breaker
        if not await self.circuit_breaker.can_execute():
            logger.warning("Email request blocked by circuit breaker (service unavailable)")
            return EmailResponse(
                success=False,
                error="Email service temporarily unavailable (circuit breaker open)",
            )

        last_error: str | None = None
        endpoint = f"{self.base_url}/emails"

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        endpoint,
                        json=request.to_dict(),
                        headers=self._get_headers(),
                    )

                    # Success (202 Accepted)
                    if response.status_code == 202:
                        data = response.json()
                        await self.circuit_breaker.record_success()
                        logger.info(
                            f"Email queued successfully: message_id={data.get('message_id')}, "
                            f"to={request.to[0] if request.to else 'unknown'}"
                        )
                        return EmailResponse(
                            success=True,
                            message_id=data.get("message_id"),
                            queued=True,
                        )

                    # Client error (4xx) - don't retry
                    if 400 <= response.status_code < 500:
                        error_data = response.json() if response.content else {}
                        error_msg = error_data.get("message", f"HTTP {response.status_code}")
                        logger.warning(f"Email request rejected: {error_msg}")
                        return EmailResponse(success=False, error=error_msg)

                    # Server error (5xx) - retry
                    last_error = f"HTTP {response.status_code}"
                    logger.warning(
                        f"Email service error (attempt {attempt + 1}/{self.max_retries + 1}): "
                        f"{last_error}"
                    )

            except httpx.TimeoutException:
                last_error = "Request timeout"
                logger.warning(
                    f"Email service timeout (attempt {attempt + 1}/{self.max_retries + 1})"
                )

            except httpx.ConnectError:
                last_error = "Connection failed"
                logger.warning(
                    f"Email service connection failed (attempt {attempt + 1}/{self.max_retries + 1})"
                )

            except Exception as e:
                last_error = str(e)
                logger.exception(f"Unexpected error sending email: {e}")
                break  # Don't retry on unexpected errors

            # Exponential backoff before retry
            if attempt < self.max_retries:
                delay = self.retry_delay * (2**attempt)
                logger.debug(f"Retrying in {delay:.2f}s...")
                await asyncio.sleep(delay)

        # All retries exhausted
        await self.circuit_breaker.record_failure()
        logger.error(f"Email send failed after {self.max_retries + 1} attempts: {last_error}")
        return EmailResponse(success=False, error=last_error)

    async def send_email(
        self,
        to: list[str],
        subject: str,
        body: str,
        template_id: str | None = None,
        template_vars: dict[str, Any] | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        client_message_id: str | None = None,
    ) -> EmailResponse:
        """Send email via HTTP service (fire-and-forget semantics).

        This method is designed to NEVER block or fail critical operations.
        Errors are logged but do not propagate.

        Args:
            to: List of recipient email addresses
            subject: Email subject line
            body: HTML email body
            template_id: Optional template identifier
            template_vars: Optional template variables
            cc: Optional CC recipients
            bcc: Optional BCC recipients
            metadata: Optional tracking metadata
            client_message_id: Optional client-side tracking ID

        Returns:
            EmailResponse with success status and message_id if queued
        """
        if not self.enabled:
            logger.debug("Email sending disabled, skipping")
            return EmailResponse(success=False, error="Email service disabled")

        if not to:
            logger.warning("No recipients provided for email")
            return EmailResponse(success=False, error="No recipients")

        request = EmailRequest(
            to=to,
            subject=subject,
            body=body,
            template_id=template_id,
            template_vars=template_vars,
            cc=cc,
            bcc=bcc,
            metadata=metadata,
            client_message_id=client_message_id,
        )

        return await self._execute_with_retry(request)

    async def send_email_fire_and_forget(
        self,
        to: list[str],
        subject: str,
        body: str,
        template_id: str | None = None,
        template_vars: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Send email without waiting for response (true fire-and-forget).

        This method returns immediately and processes the email in the background.
        Use this when you don't need to know if the email was queued.

        Args:
            to: List of recipient email addresses
            subject: Email subject line
            body: HTML email body
            template_id: Optional template identifier
            template_vars: Optional template variables
            **kwargs: Additional email parameters
        """
        if not self.enabled:
            logger.debug("Email service disabled, skipping fire-and-forget")
            return

        # Schedule email sending as background task
        # Store reference to prevent garbage collection
        task = asyncio.create_task(
            self._fire_and_forget_wrapper(
                to=to,
                subject=subject,
                body=body,
                template_id=template_id,
                template_vars=template_vars,
                **kwargs,
            )
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        logger.debug(f"Email scheduled (fire-and-forget): to={to[0] if to else 'unknown'}")

    async def _fire_and_forget_wrapper(self, **kwargs: Any) -> None:
        """Wrapper to catch and log errors in fire-and-forget mode."""
        try:
            await self.send_email(**kwargs)
        except Exception as e:
            logger.error(f"Fire-and-forget email failed: {e}")

    async def check_health(self) -> dict[str, Any]:
        """Check email service health.

        Returns:
            dict with health status and details
        """
        if not self.enabled:
            return {"status": "disabled", "enabled": False}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/health",
                    headers={"Accept": "application/json"},
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "status": "healthy",
                        "enabled": True,
                        "service_status": data.get("status"),
                        "db": data.get("db"),
                        "email_provider": data.get("email_provider"),
                    }
                return {
                    "status": "unhealthy",
                    "enabled": True,
                    "error": f"HTTP {response.status_code}",
                }

        except Exception as e:
            return {
                "status": "unreachable",
                "enabled": True,
                "error": str(e),
            }


# Singleton instance
_email_client: EmailServiceClient | None = None


def get_email_client() -> EmailServiceClient:
    """Get or create singleton email service client.

    Returns:
        EmailServiceClient instance
    """
    global _email_client
    if _email_client is None:
        _email_client = EmailServiceClient()
    return _email_client


# Convenience functions for fire-and-forget usage
async def send_booking_email(
    customer_email: str,
    customer_name: str,
    booking_id: int,
    service_type: str,
    booking_date: str,
    booking_time: str,
    template_id: str,
    calendar_link: str | None = None,
    **extra_vars: Any,
) -> None:
    """Send booking-related email (fire-and-forget).

    This is a convenience function for booking notifications.
    Failures are logged but never block booking operations.

    Args:
        customer_email: Recipient email
        customer_name: Customer name for personalization
        booking_id: Booking ID for tracking
        service_type: Type of service booked
        booking_date: Date of booking (YYYY-MM-DD)
        booking_time: Time of booking (HH:MM)
        template_id: Email template (booking_created, booking_cancelled, etc.)
        calendar_link: Optional Google Calendar link
        **extra_vars: Additional template variables
    """
    client = get_email_client()

    template_vars = {
        "customer_name": customer_name,
        "booking_id": booking_id,
        "service_type": service_type,
        "booking_date": booking_date,
        "booking_time": booking_time,
        "google_calendar_link": calendar_link,
        **extra_vars,
    }

    # Build subject based on template
    subject_map = {
        "booking_created": f"Booking Confirmation - {service_type}",
        "booking_cancelled": f"Booking Cancelled - {service_type}",
        "booking_rescheduled": f"Booking Rescheduled - {service_type}",
        "reminder_24h": f"Reminder: Your appointment tomorrow - {service_type}",
        "reminder_1h": f"Reminder: Your appointment in 1 hour - {service_type}",
    }
    subject = subject_map.get(template_id, f"Booking Update - {service_type}")

    await client.send_email_fire_and_forget(
        to=[customer_email],
        subject=subject,
        body="",  # Template will generate body
        template_id=template_id,
        template_vars=template_vars,
        metadata={"booking_id": booking_id},
    )


async def send_otp_email(
    recipient_email: str,
    recipient_name: str,
    otp_code: str,
    expiry_minutes: int = 10,
    language: str = "es",
) -> None:
    """Send OTP verification email (fire-and-forget).

    Args:
        recipient_email: Email address to send OTP
        recipient_name: Recipient name for personalization
        otp_code: 6-digit OTP code
        expiry_minutes: Minutes until OTP expires
        language: Language for email content (es/en)
    """
    client = get_email_client()

    subject = (
        f"Código de verificación: {otp_code}"
        if language == "es"
        else f"Verification Code: {otp_code}"
    )

    await client.send_email_fire_and_forget(
        to=[recipient_email],
        subject=subject,
        body="",  # Template will generate body
        template_id="otp_verification",
        template_vars={
            "recipient_name": recipient_name,
            "otp_code": otp_code,
            "expiry_minutes": expiry_minutes,
            "language": language,
        },
    )
