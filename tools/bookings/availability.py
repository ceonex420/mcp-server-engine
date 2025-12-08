"""Availability checking for booking system.

Provides functions for checking slot availability and finding open dates.
All operations are async for non-blocking database access.

Author: Odiseo Team
Version: 2.0.0
"""

from __future__ import annotations

from datetime import date as date_type, datetime, time as time_type, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from config.settings import settings
from utils.db_async import fetchone_async
from utils.logger import get_logger
from utils.validation import validate_schema_name

# Day names in English (fallback)
DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Get module logger
logger = get_logger("mcp_tools_bookings_availability")


async def get_available_slots_async(
    service_type: str,
    date: str,
    duration_minutes: int = 60,
) -> dict[str, Any]:
    """Get available time slots for a specific date and service.

    Filters out past times and slots that don't meet minimum advance requirement.
    Checks business hours, existing bookings, and blocked times.

    Args:
        service_type: Type of service (used for duration lookup).
        date: Date to check in YYYY-MM-DD format.
        duration_minutes: Required appointment duration (default: 60).

    Returns:
        Dict with available slots and metadata.
    """
    logger.info(f"Getting available slots for {service_type} on {date}")

    validate_schema_name(settings.SCHEMA_NAME)

    # Get current datetime for filtering (timezone-aware)
    tz = ZoneInfo(settings.GOOGLE_CALENDAR_TIMEZONE)
    now = datetime.now(tz)
    current_date = now.date()
    current_datetime = now
    min_advance_minutes = settings.BOOKING_MIN_ADVANCE_MINUTES

    # Get day of week
    try:
        dt = datetime.fromisoformat(date)
        day_of_week = dt.weekday()
        logger.debug(f"Date {date} is day {day_of_week} of week")

    except ValueError as exc:
        logger.exception(f"Invalid date format: {date}")
        raise ValueError(f"Invalid date format: {date}") from exc

    # Get business hours
    try:
        business_hours = await fetchone_async(
            f"""
            SELECT open_time, close_time
            FROM {settings.SCHEMA_NAME}.business_hours
            WHERE day_of_week = $1 AND active = true
            """,
            day_of_week,
        )

        if not business_hours:
            logger.info(f"No business hours for day {day_of_week} - closed")
            return {
                "date": date,
                "service_type": service_type,
                "available_slots": [],
                "count": 0,
                "business_hours": None,
                "min_advance_minutes": min_advance_minutes,
            }

        open_time = business_hours["open_time"]
        close_time = business_hours["close_time"]
        logger.debug(f"Business hours: {open_time} - {close_time}")

    except Exception as exc:
        logger.exception(f"Failed to fetch business hours: {exc}")
        raise RuntimeError(f"Could not fetch business hours: {exc}") from exc

    # Generate time slots
    slots = []
    current_time = datetime.combine(dt, open_time, tzinfo=tz)
    end_time = datetime.combine(dt, close_time, tzinfo=tz)
    interval = timedelta(minutes=settings.BOOKING_SLOT_INTERVAL_MINUTES)
    min_advance_delta = timedelta(minutes=min_advance_minutes)

    while current_time < end_time:
        time_str = current_time.strftime("%H:%M")

        # Skip past times (only for today)
        if dt.date() == current_date and current_time < current_datetime:
            logger.debug(f"Skipping {time_str} - time has already passed")
            current_time += interval
            continue

        # Skip times that don't meet minimum advance requirement
        min_allowed_booking_time = current_datetime + min_advance_delta
        if current_time < min_allowed_booking_time:
            logger.debug(f"Skipping {time_str} - does not meet minimum advance requirement")
            current_time += interval
            continue

        # Check if slot is available
        try:
            query = (
                f"SELECT {settings.SCHEMA_NAME}.is_slot_available"
                f"($1, $2, $3, $4) as available"
            )
            # Convert to Python date/time objects for asyncpg
            date_obj = dt.date()
            time_obj = current_time.time()

            availability = await fetchone_async(
                query,
                date_obj, time_obj, duration_minutes, service_type,
            )

            is_available = availability["available"] if availability else False
            slots.append({"time": time_str, "available": is_available})

        except Exception as exc:
            logger.warning(f"Failed to check availability for {time_str}: {exc}")
            slots.append({"time": time_str, "available": False})

        current_time += interval

    available_count = sum(1 for s in slots if s["available"])
    logger.info(
        f"Generated {len(slots)} time slots for {date} "
        f"({available_count} available, min_advance: {min_advance_minutes} min)"
    )

    return {
        "date": date,
        "service_type": service_type,
        "available_slots": slots,
        "count": available_count,
        "business_hours": {
            "open_time": str(open_time),
            "close_time": str(close_time),
        },
        "min_advance_minutes": min_advance_minutes,
    }


async def find_first_available_slots_in_range_async(
    service_type: str,
    start_date: str,
    end_date: str,
    duration_minutes: int = 60,
) -> dict[str, Any]:
    """Find the first available date with slots within a date range.

    Searches through multiple days to find the FIRST date that has
    available time slots.

    Args:
        service_type: Type of service to check availability for.
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format (inclusive).
        duration_minutes: Required appointment duration (default: 60).

    Returns:
        Dict with first available date and slots.
    """
    logger.info(
        f"Searching for first available {service_type} slots between {start_date} and {end_date}"
    )

    try:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)

        if start_dt > end_dt:
            logger.warning(f"Invalid date range: {start_date} > {end_date}")
            raise ValueError("Invalid date range: start_date must be before end_date")

        current_dt = start_dt
        days_searched = 0

        while current_dt <= end_dt:
            date_str = current_dt.strftime("%Y-%m-%d")
            day_name = DAYS_OF_WEEK[current_dt.weekday()]

            logger.debug(f"Checking availability for {date_str} ({day_name})")

            try:
                result = await get_available_slots_async(service_type, date_str, duration_minutes)
                days_searched += 1

                available = [s for s in result["available_slots"] if s["available"]]

                if available:
                    available_times = [s["time"] for s in available]

                    logger.info(
                        f"Found {len(available)} available slots on {date_str} ({day_name})"
                    )

                    date_formatted = current_dt.strftime("%Y-%m-%d")

                    return {
                        "found": True,
                        "first_available_date": date_str,
                        "first_available_day_name": day_name,
                        "first_available_date_formatted": f"{day_name} {date_formatted}",
                        "available_slots": available_times,
                        "available_count": len(available),
                        "days_searched": days_searched,
                        "duration_minutes": duration_minutes,
                    }

            except Exception as exc:
                logger.debug(f"Error checking {date_str}: {exc}")

            current_dt += timedelta(days=1)

        # No available dates found
        logger.info(f"No availability found between {start_date} and {end_date}")

        return {
            "found": False,
            "first_available_date": None,
            "first_available_day_name": None,
            "available_slots": None,
            "days_searched": days_searched,
            "duration_minutes": duration_minutes,
        }

    except Exception as exc:
        logger.exception(f"Error searching for available slots: {exc}")
        raise RuntimeError(f"Could not search for available slots: {exc}") from exc
