"""Core booking operations: create, cancel, reschedule.

Provides the main CRUD operations for booking management.
All operations are async for non-blocking database access.

Author: Odiseo Team
Version: 2.0.0
"""

from __future__ import annotations

from typing import Any

from config.booking_constants import BookingStatus
from config.settings import settings
from utils.db_async import fetchone_async
from utils.logger import get_logger
from utils.validation import validate_email, validate_schema_name

from .calendar import (
    create_calendar_event,
    delete_calendar_event,
    get_calendar_client,
    get_calendar_link,
    update_calendar_event,
)
from .email import (
    send_booking_cancelled_email,
    send_booking_created_email,
    send_booking_rescheduled_email,
)
from .helpers import create_booking_atomic_async, parse_booking_datetime

# Get module logger
logger = get_logger("mcp_tools_bookings_core")


async def create_booking_async(
    customer_name: str,
    customer_email: str,
    customer_phone: str,
    service_type: str,
    booking_date: str,
    booking_time: str,
    notes: str,
    duration_minutes: int = 60,
) -> dict[str, Any]:
    """Create a new booking/reservation.

    Creates appointment in database and optionally in Google Calendar.

    Args:
        customer_name: Customer full name.
        customer_email: Customer email address.
        customer_phone: Customer phone number.
        service_type: Type of service being booked.
        booking_date: Booking date in YYYY-MM-DD format.
        booking_time: Booking time in HH:MM format (24-hour).
        notes: REQUIRED. Reason or purpose of the appointment.
        duration_minutes: Appointment duration (default: 60).

    Returns:
        Dict with booking details.

    Raises:
        ValueError: If validation fails or slot unavailable.
        RuntimeError: If database or calendar operation fails.
    """
    logger.info(f"Creating booking for {customer_email} on {booking_date} at {booking_time}")

    # Validate email format
    is_valid_email, email_error = validate_email(customer_email)
    if not is_valid_email:
        logger.warning(f"Email validation failed: {email_error}")
        raise ValueError(email_error)

    # Validate notes are provided
    if not notes or not notes.strip():
        logger.warning("Notes validation failed: Notes/motivo is required")
        raise ValueError(
            "Notes are required. Please provide the reason or purpose of the appointment."
        )

    # Validate availability
    validate_schema_name(settings.SCHEMA_NAME)
    try:
        # Parse strings to date/time objects for asyncpg
        date_obj, time_obj = parse_booking_datetime(booking_date, booking_time)

        availability_check = await fetchone_async(
            f"SELECT {settings.SCHEMA_NAME}.is_slot_available($1, $2, $3, $4) as available",
            date_obj,
            time_obj,
            duration_minutes,
            service_type,
        )

        if not availability_check or not availability_check["available"]:
            raise ValueError(f"Time slot {booking_date} at {booking_time} is not available")

        logger.debug("Availability check passed")

    except ValueError:
        raise
    except Exception as exc:
        logger.exception(f"Availability check failed: {exc}")
        raise ValueError(f"Failed to verify availability: {exc}") from exc

    # Create Google Calendar event (sync - external API)
    calendar_event_id, calendar_link = create_calendar_event(
        customer_name=customer_name,
        customer_email=customer_email,
        service_type=service_type,
        booking_date=booking_date,
        booking_time=booking_time,
        duration_minutes=duration_minutes,
        notes=notes,
    )

    # Insert into database atomically
    calendar_client = get_calendar_client()
    try:
        db_result = await create_booking_atomic_async(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            service_type=service_type,
            booking_date=booking_date,
            booking_time=booking_time,
            duration_minutes=duration_minutes,
            notes=notes,
            calendar_event_id=calendar_event_id,
            calendar_link=calendar_link,
        )

        booking_id = db_result["id"]
        logger.info(f"Booking created successfully: ID={booking_id}")

        booking_response = {
            "booking_id": booking_id,
            "status": db_result["status"],
            "google_calendar_event_id": calendar_event_id,
            "google_calendar_link": calendar_link,
            "booking_date": booking_date,
            "booking_time": booking_time,
            "duration_minutes": duration_minutes,
            "created_at": db_result["created_at"],
        }

    except Exception as exc:
        logger.exception(f"Failed to create booking in database: {exc}")

        # Rollback calendar event
        if calendar_event_id and calendar_client:
            delete_calendar_event(calendar_event_id, send_notifications=False)
            logger.info("Rolled back Google Calendar event")

        raise RuntimeError(f"Failed to create booking: {exc}") from exc

    # Send confirmation email (fire-and-forget)
    send_booking_created_email(
        booking_id=booking_id,
        customer_name=customer_name,
        customer_email=customer_email,
        service_type=service_type,
        booking_date=booking_date,
        booking_time=booking_time,
        duration_minutes=duration_minutes,
        calendar_link=calendar_link,
    )

    return booking_response


async def cancel_booking_async(
    booking_id: int,
    cancellation_reason: str = "",
) -> dict[str, Any]:
    """Cancel an existing booking.

    Updates database status and deletes Google Calendar event.

    Args:
        booking_id: ID of booking to cancel.
        cancellation_reason: Reason for cancellation (optional).

    Returns:
        Dict with cancellation confirmation.

    Raises:
        ValueError: If booking not found or already cancelled.
        RuntimeError: If cancellation fails.
    """
    logger.info(f"Cancelling booking: {booking_id}")

    # Fetch booking details
    validate_schema_name(settings.SCHEMA_NAME)
    try:
        booking = await fetchone_async(
            f"SELECT * FROM {settings.SCHEMA_NAME}.appointments WHERE id = $1",
            booking_id,
        )

        if not booking:
            raise ValueError(f"Booking {booking_id} not found")

        if booking["status"] == BookingStatus.CANCELLED.value:
            raise ValueError(f"Booking {booking_id} is already cancelled")

        logger.debug(f"Found booking: {booking['customer_name']} on {booking['booking_date']}")

    except ValueError:
        raise
    except Exception as exc:
        logger.exception(f"Failed to fetch booking: {exc}")
        raise RuntimeError(f"Failed to fetch booking {booking_id}: {exc}") from exc

    # Delete Google Calendar event (sync - external API)
    calendar_deleted = False
    if booking["google_calendar_event_id"]:
        calendar_deleted = delete_calendar_event(booking["google_calendar_event_id"])

    # Update database
    try:
        update_sql = f"""
        UPDATE {settings.SCHEMA_NAME}.appointments
        SET status = $1,
            cancellation_reason = $2,
            cancelled_at = CURRENT_TIMESTAMP
        WHERE id = $3
        RETURNING cancelled_at
        """

        result = await fetchone_async(
            update_sql,
            BookingStatus.CANCELLED.value,
            cancellation_reason,
            booking_id,
        )

        if not result:
            raise RuntimeError("Failed to cancel booking: no result returned")

        logger.info(f"Booking cancelled successfully: ID={booking_id}")

        cancellation_response = {
            "booking_id": booking_id,
            "status": "cancelled",
            "cancelled_at": str(result["cancelled_at"]),
            "calendar_event_deleted": calendar_deleted,
        }

    except Exception as exc:
        logger.exception(f"Failed to cancel booking in database: {exc}")
        raise RuntimeError(f"Failed to cancel booking: {exc}") from exc

    # Send cancellation email (fire-and-forget)
    send_booking_cancelled_email(
        booking_id=booking_id,
        customer_name=booking["customer_name"],
        customer_email=booking["customer_email"],
        service_type=booking["service_type"],
        booking_date=str(booking["booking_date"]),
        booking_time=str(booking["booking_time"]),
        cancellation_reason=cancellation_reason,
    )

    return cancellation_response


async def reschedule_booking_async(
    booking_id: int,
    new_date: str,
    new_time: str,
) -> dict[str, Any]:
    """Reschedule an existing booking to a new date/time.

    Updates database and Google Calendar event.

    Args:
        booking_id: ID of booking to reschedule.
        new_date: New booking date in YYYY-MM-DD format.
        new_time: New booking time in HH:MM format.

    Returns:
        Dict with updated booking details.

    Raises:
        ValueError: If booking not found, slot unavailable, or invalid status.
        RuntimeError: If reschedule operation fails.
    """
    logger.info(f"Rescheduling booking {booking_id} to {new_date} at {new_time}")

    # Fetch booking details
    validate_schema_name(settings.SCHEMA_NAME)
    try:
        booking = await fetchone_async(
            f"SELECT * FROM {settings.SCHEMA_NAME}.appointments WHERE id = $1",
            booking_id,
        )

        if not booking:
            raise ValueError(f"Booking {booking_id} not found")

        non_reschedulable = {s.value for s in BookingStatus.non_reschedulable()}
        if booking["status"] in non_reschedulable:
            raise ValueError(f"Cannot reschedule booking with status: {booking['status']}")

        logger.debug(f"Found booking: {booking['customer_name']}")

    except ValueError:
        raise
    except Exception as exc:
        logger.exception(f"Failed to fetch booking: {exc}")
        raise RuntimeError(f"Failed to fetch booking {booking_id}: {exc}") from exc

    # Check availability of new slot
    try:
        # Parse strings to date/time objects for asyncpg
        new_date_obj, new_time_obj = parse_booking_datetime(new_date, new_time)

        availability_check = await fetchone_async(
            f"SELECT {settings.SCHEMA_NAME}.is_slot_available($1, $2, $3, $4) as available",
            new_date_obj,
            new_time_obj,
            booking["duration_minutes"],
            booking["service_type"],
        )

        if not availability_check or not availability_check["available"]:
            raise ValueError(f"Time slot {new_date} at {new_time} is not available")

        logger.debug("New slot is available")

    except ValueError:
        raise
    except Exception as exc:
        logger.exception(f"Availability check failed: {exc}")
        raise RuntimeError(f"Failed to verify availability: {exc}") from exc

    # Update Google Calendar event (sync - external API)
    calendar_updated = False
    calendar_link = booking.get("google_calendar_link")

    if booking["google_calendar_event_id"]:
        calendar_updated = update_calendar_event(
            event_id=booking["google_calendar_event_id"],
            new_date=new_date,
            new_time=new_time,
            duration_minutes=booking["duration_minutes"],
        )

    # Get calendar link if missing
    if (
        not calendar_link
        and settings.GOOGLE_CALENDAR_ENABLED
        and booking["google_calendar_event_id"]
    ):
        calendar_link = get_calendar_link(booking["google_calendar_event_id"])

    # Update database
    try:
        update_sql = f"""
        UPDATE {settings.SCHEMA_NAME}.appointments
        SET booking_date = $1,
            booking_time = $2,
            status = $3,
            google_calendar_link = $4
        WHERE id = $5
        RETURNING booking_date, booking_time, status, google_calendar_link
        """

        result = await fetchone_async(
            update_sql,
            new_date_obj,
            new_time_obj,
            BookingStatus.RESCHEDULED.value,
            calendar_link,
            booking_id,
        )

        if not result:
            raise RuntimeError("Failed to reschedule booking: no result returned")

        logger.info(f"Booking rescheduled successfully: ID={booking_id}")

        updated_calendar_link = result.get("google_calendar_link") or calendar_link

        reschedule_response = {
            "booking_id": booking_id,
            "status": result["status"],
            "new_date": str(result["booking_date"]),
            "new_time": str(result["booking_time"]),
            "calendar_event_updated": calendar_updated,
            "google_calendar_link": updated_calendar_link,
        }

    except Exception as exc:
        logger.exception(f"Failed to reschedule booking in database: {exc}")
        raise RuntimeError(f"Failed to reschedule booking: {exc}") from exc

    # Send rescheduled email (fire-and-forget)
    send_booking_rescheduled_email(
        booking_id=booking_id,
        customer_name=booking["customer_name"],
        customer_email=booking["customer_email"],
        service_type=booking["service_type"],
        new_date=new_date,
        new_time=new_time,
        old_date=str(booking["booking_date"]),
        old_time=str(booking["booking_time"]),
        calendar_link=updated_calendar_link,
    )

    return reschedule_response
