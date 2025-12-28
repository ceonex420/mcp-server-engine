"""Query functions for booking data retrieval.

Provides read-only functions for fetching booking data.
All operations are async for non-blocking database access.

Author: Odiseo Team
Version: 2.0.0
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from config.booking_constants import BookingStatus
from config.settings import settings
from utils.db_async import fetchall_async, fetchone_async
from utils.logger import get_logger
from utils.pagination import PaginatedResponse, PaginationDefaults, PaginationParams
from utils.validation import validate_schema_name

# Get module logger
logger = get_logger("mcp_tools_bookings_queries")


async def get_booking_by_id_async(booking_id: int) -> dict[str, Any] | None:
    """Get booking details by ID.

    Args:
        booking_id: Booking ID to fetch.

    Returns:
        Booking details dict or None if not found.
    """
    logger.debug(f"Fetching booking by ID: {booking_id}")
    validate_schema_name(settings.SCHEMA_NAME)

    try:
        booking = await fetchone_async(
            f"""
            SELECT id, customer_name, customer_email, customer_phone,
                   service_type, booking_date, booking_time, duration_minutes,
                   status, notes, google_calendar_link,
                   created_at, updated_at
            FROM {settings.SCHEMA_NAME}.appointments
            WHERE id = $1
            """,
            booking_id,
        )

        if booking:
            booking["booking_date"] = str(booking["booking_date"])
            booking["booking_time"] = str(booking["booking_time"])
            booking["created_at"] = str(booking["created_at"])
            booking["updated_at"] = str(booking["updated_at"])
            logger.debug(f"Found booking: {booking['customer_name']}")
        else:
            logger.debug(f"Booking {booking_id} not found")

        return booking

    except Exception as exc:
        logger.exception(f"Failed to fetch booking: {exc}")
        raise RuntimeError(f"Could not fetch booking {booking_id}: {exc}") from exc


async def list_customer_bookings_async(
    customer_email: str,
    include_cancelled: bool = False,
    limit: int = PaginationDefaults.LIST_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """List all bookings for a customer with pagination support.

    Args:
        customer_email: Customer email address.
        include_cancelled: Include cancelled bookings (default: False).
        limit: Maximum number of bookings to return (default: 50, max: 100).
        offset: Number of bookings to skip for pagination (default: 0).

    Returns:
        PaginatedResponse dict with booking list, counts, and pagination metadata.
    """
    page_params = PaginationParams.for_list(limit=limit, offset=offset)

    logger.info(
        f"Listing bookings for customer: {customer_email} "
        f"(limit={page_params.limit}, offset={page_params.offset})"
    )
    validate_schema_name(settings.SCHEMA_NAME)

    try:
        status_filter = (
            "" if include_cancelled else f"AND status != '{BookingStatus.CANCELLED.value}'"
        )

        # First, get total count for pagination info
        count_query = f"""
        SELECT COUNT(*) as total
        FROM {settings.SCHEMA_NAME}.appointments
        WHERE customer_email = $1
        {status_filter}
        """
        count_result = await fetchone_async(count_query, customer_email)
        total_count = count_result["total"] if count_result else 0

        query = f"""
        SELECT id, customer_name, customer_email, service_type,
               booking_date, booking_time, duration_minutes,
               status, google_calendar_link, created_at
        FROM {settings.SCHEMA_NAME}.appointments
        WHERE customer_email = $1
        {status_filter}
        ORDER BY booking_date DESC, booking_time DESC
        LIMIT $2 OFFSET $3
        """

        bookings = await fetchall_async(
            query, customer_email, page_params.limit, page_params.offset
        )

        # Get current datetime for past/future filtering (timezone-aware)
        tz = ZoneInfo(settings.GOOGLE_CALENDAR_TIMEZONE)
        now = datetime.now(tz)
        current_date = now.date()
        current_time = now.time()

        for booking in bookings:
            booking["booking_date"] = str(booking["booking_date"])
            booking["booking_time"] = str(booking["booking_time"])
            booking["created_at"] = str(booking["created_at"])

            try:
                booking_date = datetime.fromisoformat(str(booking["booking_date"])).date()
                booking_time = datetime.fromisoformat(
                    f"1970-01-01T{booking['booking_time']}"
                ).time()

                is_past = booking_date < current_date or (
                    booking_date == current_date and booking_time < current_time
                )
                booking["is_past"] = is_past

            except (ValueError, AttributeError) as exc:
                logger.warning(f"Could not parse booking datetime: {exc}")
                booking["is_past"] = False

        active_count = sum(1 for b in bookings if b.get("status") != BookingStatus.CANCELLED.value)
        future_count = sum(
            1
            for b in bookings
            if not b.get("is_past", False) and b.get("status") != BookingStatus.CANCELLED.value
        )

        logger.info(
            f"Found {len(bookings)} bookings for {customer_email} "
            f"({active_count} active, {future_count} future, total={total_count})"
        )

        response = PaginatedResponse.create(
            items=bookings,
            total_count=total_count,
            params=page_params,
            customer_email=customer_email,
            active_count=active_count,
            future_count=future_count,
        )

        return response.to_dict()

    except Exception as exc:
        logger.exception(f"Failed to list bookings: {exc}")
        raise RuntimeError(f"Could not list bookings for {customer_email}: {exc}") from exc


async def get_services_async(active_only: bool = True) -> dict[str, Any]:
    """Get available booking services from database.

    Args:
        active_only: Only return active services (default: True).

    Returns:
        Dict with services list and total count.
    """
    logger.info("Fetching services from database")
    validate_schema_name(settings.SCHEMA_NAME)

    try:
        query = f"""
        SELECT
            name,
            display_name,
            description,
            duration_minutes,
            price,
            color,
            icon
        FROM {settings.SCHEMA_NAME}.service_types
        WHERE active = $1
        ORDER BY display_name
        """

        rows = await fetchall_async(query, active_only)

        services = [
            {
                "name": row["name"],
                "display_name": row["display_name"],
                "description": row["description"],
                "duration_minutes": row["duration_minutes"],
                "price": float(row["price"]),
                "color": row["color"],
                "icon": row["icon"],
            }
            for row in rows
        ]

        logger.info(f"Loaded {len(services)} services from database")

        return {"services": services, "total": len(services)}

    except Exception as exc:
        logger.exception(f"Failed to fetch services: {exc}")
        raise RuntimeError(f"Could not fetch services: {exc}") from exc


async def get_business_hours_async() -> dict[str, Any]:
    """Get business operating hours from database.

    Returns:
        Dict with hours by day and timezone info.
    """
    logger.info("Fetching business hours from database")
    validate_schema_name(settings.SCHEMA_NAME)

    try:
        query = f"""
        SELECT
            day_of_week,
            open_time,
            close_time
        FROM {settings.SCHEMA_NAME}.business_hours
        WHERE active = true
        ORDER BY day_of_week
        """

        rows = await fetchall_async(query)

        days_map = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        hours = {}

        for row in rows:
            day_index = row["day_of_week"]
            if 0 <= day_index < len(days_map):
                day_name = days_map[day_index]
                hours[day_name] = {
                    "open": str(row["open_time"]),
                    "close": str(row["close_time"]),
                }

        logger.info(f"Loaded business hours for {len(hours)} days")

        return {
            "hours": hours,
            "timezone": settings.GOOGLE_CALENDAR_TIMEZONE,
            "days_count": len(hours),
        }

    except Exception as exc:
        logger.exception(f"Failed to fetch business hours: {exc}")
        raise RuntimeError(f"Could not fetch business hours: {exc}") from exc
