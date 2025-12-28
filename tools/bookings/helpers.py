"""Helper functions for booking operations.

Provides internal utilities for atomic transactions and data formatting.
All operations are async for non-blocking database access.

Author: Odiseo Team
Version: 2.0.0
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from config.booking_constants import BookingStatus
from config.settings import settings
from utils.db_async import get_conn_async
from utils.logger import get_logger
from utils.validation import validate_schema_name

# Get module logger
logger = get_logger("mcp_tools_bookings_helpers")


def parse_booking_datetime(booking_date: str, booking_time: str) -> tuple[date, time]:
    """Parse booking date and time strings to Python objects.

    Args:
        booking_date: Date string in YYYY-MM-DD format
        booking_time: Time string in HH:MM format

    Returns:
        Tuple of (date, time) objects for asyncpg compatibility
    """
    date_obj = date.fromisoformat(booking_date)
    time_obj = time.fromisoformat(booking_time)
    return date_obj, time_obj


async def create_booking_atomic_async(
    customer_name: str,
    customer_email: str,
    customer_phone: str,
    service_type: str,
    booking_date: str,
    booking_time: str,
    duration_minutes: int,
    notes: str,
    calendar_event_id: str | None = None,
    calendar_link: str | None = None,
) -> dict[str, Any]:
    """Create a booking with atomic transaction and row-level locking.

    Uses PostgreSQL row-level locking (SELECT ... FOR UPDATE) to prevent
    race conditions when concurrent requests check availability.

    Args:
        customer_name: Customer name
        customer_email: Customer email
        customer_phone: Customer phone
        service_type: Service type
        booking_date: Booking date (YYYY-MM-DD)
        booking_time: Booking time (HH:MM)
        duration_minutes: Duration in minutes
        notes: Booking notes
        calendar_event_id: Optional Google Calendar event ID
        calendar_link: Optional Google Calendar link

    Returns:
        Dict with booking details (id, status, created_at)

    Raises:
        RuntimeError: If booking creation fails or slot becomes unavailable
    """
    validate_schema_name(settings.SCHEMA_NAME)

    try:
        async with get_conn_async() as conn, conn.transaction():
            logger.debug(f"Starting atomic booking transaction for {booking_date} {booking_time}")

            # Parse strings to date/time objects for asyncpg
            date_obj, time_obj = parse_booking_datetime(booking_date, booking_time)
            booking_dt = datetime.fromisoformat(f"{booking_date}T{booking_time}:00")
            end_time_dt = booking_dt + timedelta(minutes=duration_minutes)

            # Lock overlapping appointments
            lock_query = f"""
                SELECT id
                FROM {settings.SCHEMA_NAME}.appointments
                WHERE booking_date = $1
                  AND status IN ('confirmed', 'rescheduled')
                  AND booking_time < $2
                  AND booking_time + (duration_minutes || ' minutes')::INTERVAL > $3
                FOR UPDATE
            """

            locked_rows = await conn.fetch(
                lock_query, date_obj, end_time_dt.time(), booking_dt.time()
            )
            logger.debug(f"Locked {len(locked_rows)} overlapping appointments")

            # Recheck availability
            availability_check_query = f"""
                SELECT {settings.SCHEMA_NAME}.is_slot_available($1, $2, $3, $4) as available
            """
            availability_result = await conn.fetchrow(
                availability_check_query,
                date_obj,
                time_obj,
                duration_minutes,
                service_type,
            )
            is_available = availability_result["available"] if availability_result else False

            if not is_available:
                logger.warning(
                    f"Slot {booking_date} {booking_time} became unavailable after locking"
                )
                raise RuntimeError(
                    f"Time slot {booking_date} at {booking_time} is no longer available"
                )

            # Insert booking
            insert_query = f"""
                INSERT INTO {settings.SCHEMA_NAME}.appointments
                (customer_name, customer_email, customer_phone, service_type,
                 booking_date, booking_time, duration_minutes, notes,
                 google_calendar_event_id, google_calendar_link, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING id, status, created_at
            """

            result = await conn.fetchrow(
                insert_query,
                customer_name,
                customer_email,
                customer_phone,
                service_type,
                date_obj,
                time_obj,
                duration_minutes,
                notes,
                calendar_event_id,
                calendar_link,
                BookingStatus.CONFIRMED.value,
            )

            if not result:
                raise RuntimeError("Failed to create booking: no result returned")

            logger.info(f"Booking created atomically: ID={result['id']}")

            return {
                "id": result["id"],
                "status": result["status"],
                "created_at": str(result["created_at"]),
            }

    except Exception as exc:
        logger.exception(f"Atomic booking creation failed: {exc}")
        raise RuntimeError(f"Failed to create booking: {exc}") from exc
