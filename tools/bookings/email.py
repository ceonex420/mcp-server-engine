"""Email notification integration for booking system.

Provides fire-and-forget email notifications for booking events.
Uses HTTP client to communicate with email microservice.

Design Pattern: Fire-and-Forget with Graceful Degradation
- Emails are sent asynchronously via HTTP
- Failures are logged but NEVER block booking operations
- Circuit breaker prevents overwhelming failed service

Author: Odiseo Team
Version: 2.0.0
"""

from __future__ import annotations

import asyncio
from typing import Any

from config.booking_constants import EmailNotificationType
from config.settings import settings
from utils.email_client import get_email_client
from utils.logger import get_logger

# Get module logger
logger = get_logger("mcp_tools_bookings_email")


# Keep reference to background tasks to prevent garbage collection
_background_tasks: set[asyncio.Task[Any]] = set()


def _run_async(coro: Any) -> None:
    """Run async coroutine from sync context (fire-and-forget).

    Creates a new event loop if needed, schedules the coroutine,
    and returns immediately without waiting.

    Args:
        coro: Async coroutine to run
    """
    try:
        loop = asyncio.get_running_loop()
        # We're in an async context, schedule as task
        task = asyncio.create_task(coro)
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    except RuntimeError:
        # No running loop, create one for this operation
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(coro)
        finally:
            loop.close()


async def _send_email_async(
    email_type: str,
    customer_email: str,
    customer_name: str,
    booking_id: int,
    service_type: str,
    booking_date: str,
    booking_time: str,
    calendar_link: str | None = None,
    extra_vars: dict[str, Any] | None = None,
) -> None:
    """Send email via HTTP service (async implementation).

    This is the core async function that communicates with email service.
    Errors are caught and logged, never propagated.

    Args:
        email_type: Type of email (booking_created, etc.)
        customer_email: Recipient email address
        customer_name: Customer name for personalization
        booking_id: Booking ID for tracking
        service_type: Type of service booked
        booking_date: Date of booking
        booking_time: Time of booking
        calendar_link: Optional Google Calendar link
        extra_vars: Additional template variables
    """
    if not settings.EMAIL_SERVICE_ENABLED:
        logger.debug("Email service disabled, skipping notification")
        return

    try:
        client = get_email_client()

        # Build template variables
        template_vars: dict[str, Any] = {
            "customer_name": customer_name,
            "booking_id": booking_id,
            "service_type": service_type,
            "booking_date": booking_date,
            "booking_time": booking_time,
        }

        if calendar_link:
            template_vars["google_calendar_link"] = calendar_link

        if extra_vars:
            template_vars.update(extra_vars)

        # Map email type to template ID
        template_id_map = {
            EmailNotificationType.BOOKING_CREATED.value: "booking_created",
            EmailNotificationType.BOOKING_CANCELLED.value: "booking_cancelled",
            EmailNotificationType.BOOKING_RESCHEDULED.value: "booking_rescheduled",
        }
        template_id = template_id_map.get(email_type, "booking_created")

        # Build subject based on email type
        subject_map = {
            EmailNotificationType.BOOKING_CREATED.value: f"Booking Confirmation - {service_type}",
            EmailNotificationType.BOOKING_CANCELLED.value: f"Booking Cancelled - {service_type}",
            EmailNotificationType.BOOKING_RESCHEDULED.value: f"Booking Rescheduled - {service_type}",
        }
        subject = subject_map.get(email_type, f"Booking Update - {service_type}")

        # Send via HTTP client (fire-and-forget semantics)
        response = await client.send_email(
            to=[customer_email],
            subject=subject,
            body="",  # Template will generate body
            template_id=template_id,
            template_vars=template_vars,
            metadata={"booking_id": booking_id, "email_type": email_type},
        )

        if response.success:
            logger.info(
                f"Email sent via HTTP: type={email_type}, "
                f"message_id={response.message_id}, "
                f"recipient={customer_email}"
            )
        else:
            logger.warning(
                f"Email HTTP request failed: type={email_type}, "
                f"recipient={customer_email}, "
                f"error={response.error}"
            )

    except Exception as exc:
        # GUARANTEED: Never raises exceptions, only logs
        logger.error(
            f"Email notification error: type={email_type}, recipient={customer_email}, error={exc}"
        )


def send_booking_created_email(
    booking_id: int,
    customer_name: str,
    customer_email: str,
    service_type: str,
    booking_date: str,
    booking_time: str,
    duration_minutes: int,
    calendar_link: str | None = None,
) -> None:
    """Send booking confirmation email (fire-and-forget).

    Args:
        booking_id: Unique booking identifier
        customer_name: Customer full name
        customer_email: Customer email address
        service_type: Type of service booked
        booking_date: Date of booking (YYYY-MM-DD)
        booking_time: Time of booking (HH:MM)
        duration_minutes: Appointment duration
        calendar_link: Optional Google Calendar link
    """
    logger.debug(f"Scheduling booking created email: booking_id={booking_id}")

    _run_async(
        _send_email_async(
            email_type=EmailNotificationType.BOOKING_CREATED.value,
            customer_email=customer_email,
            customer_name=customer_name,
            booking_id=booking_id,
            service_type=service_type,
            booking_date=booking_date,
            booking_time=booking_time,
            calendar_link=calendar_link,
            extra_vars={"duration_minutes": duration_minutes},
        )
    )


def send_booking_cancelled_email(
    booking_id: int,
    customer_name: str,
    customer_email: str,
    service_type: str,
    booking_date: str,
    booking_time: str,
    cancellation_reason: str = "",
) -> None:
    """Send booking cancellation email (fire-and-forget).

    Args:
        booking_id: Unique booking identifier
        customer_name: Customer full name
        customer_email: Customer email address
        service_type: Type of service cancelled
        booking_date: Original date of booking
        booking_time: Original time of booking
        cancellation_reason: Reason for cancellation
    """
    logger.debug(f"Scheduling booking cancelled email: booking_id={booking_id}")

    _run_async(
        _send_email_async(
            email_type=EmailNotificationType.BOOKING_CANCELLED.value,
            customer_email=customer_email,
            customer_name=customer_name,
            booking_id=booking_id,
            service_type=service_type,
            booking_date=booking_date,
            booking_time=booking_time,
            extra_vars={"cancellation_reason": cancellation_reason},
        )
    )


def send_booking_rescheduled_email(
    booking_id: int,
    customer_name: str,
    customer_email: str,
    service_type: str,
    new_date: str,
    new_time: str,
    old_date: str,
    old_time: str,
    calendar_link: str | None = None,
) -> None:
    """Send booking rescheduled email (fire-and-forget).

    Args:
        booking_id: Unique booking identifier
        customer_name: Customer full name
        customer_email: Customer email address
        service_type: Type of service rescheduled
        new_date: New booking date (YYYY-MM-DD)
        new_time: New booking time (HH:MM)
        old_date: Original booking date
        old_time: Original booking time
        calendar_link: Optional Google Calendar link
    """
    logger.debug(f"Scheduling booking rescheduled email: booking_id={booking_id}")

    _run_async(
        _send_email_async(
            email_type=EmailNotificationType.BOOKING_RESCHEDULED.value,
            customer_email=customer_email,
            customer_name=customer_name,
            booking_id=booking_id,
            service_type=service_type,
            booking_date=new_date,
            booking_time=new_time,
            calendar_link=calendar_link,
            extra_vars={
                "old_date": old_date,
                "old_time": old_time,
                "new_date": new_date,
                "new_time": new_time,
            },
        )
    )
