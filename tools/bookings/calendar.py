"""Google Calendar integration for booking system.

Provides helper functions for creating, updating, and deleting
calendar events when bookings are created/modified.

Author: Odiseo Team
Version: 1.0.0
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from config.settings import settings
from utils.logger import get_logger

if TYPE_CHECKING:
    from utils.google_calendar import GoogleCalendarClient

# Get module logger
logger = get_logger("mcp_tools_bookings_calendar")

# Conditional import of Google Calendar client
_calendar_client_class: type | None = None
_calendar_error_class: type = Exception

if settings.GOOGLE_CALENDAR_ENABLED:
    try:
        from utils.google_calendar import GoogleCalendarClient, GoogleCalendarError

        _calendar_client_class = GoogleCalendarClient
        _calendar_error_class = GoogleCalendarError
        logging.info("Google Calendar client imported successfully")
    except Exception as e:
        logging.warning(f"Google Calendar client not available - {type(e).__name__}: {e}")


def get_calendar_client() -> GoogleCalendarClient | None:
    """Get Google Calendar client instance if enabled.

    Returns:
        GoogleCalendarClient instance or None if disabled/unavailable.
    """
    if not settings.GOOGLE_CALENDAR_ENABLED or not _calendar_client_class:
        return None

    try:
        return _calendar_client_class(
            credentials_path=str(settings.google_calendar_credentials_path),
            calendar_id=settings.GOOGLE_CALENDAR_ID,
            timezone=settings.GOOGLE_CALENDAR_TIMEZONE,
        )
    except Exception as exc:
        logger.exception(f"Failed to initialize Google Calendar client: {exc}")
        return None


def format_datetime_iso(booking_date: str, booking_time: str) -> str:
    """Format booking date and time to ISO 8601 string with proper timezone.

    Uses zoneinfo for DST-aware timezone handling.

    Args:
        booking_date: Date in YYYY-MM-DD format.
        booking_time: Time in HH:MM format.

    Returns:
        ISO 8601 datetime string with timezone (DST-aware).

    Example:
        >>> format_datetime_iso("2025-10-12", "15:00")
        "2025-10-12T15:00:00-05:00"  # or -04:00 if DST
    """
    dt_str = f"{booking_date}T{booking_time}:00"
    dt_naive = datetime.fromisoformat(dt_str)
    tz = ZoneInfo(settings.GOOGLE_CALENDAR_TIMEZONE)
    dt_aware = dt_naive.replace(tzinfo=tz)
    return dt_aware.isoformat()


def create_calendar_event(
    customer_name: str,
    customer_email: str,
    service_type: str,
    booking_date: str,
    booking_time: str,
    duration_minutes: int,
    notes: str = "",
) -> tuple[str | None, str | None]:
    """Create a Google Calendar event for a booking.

    Args:
        customer_name: Customer full name.
        customer_email: Customer email address.
        service_type: Type of service being booked.
        booking_date: Booking date in YYYY-MM-DD format.
        booking_time: Booking time in HH:MM format.
        duration_minutes: Appointment duration in minutes.
        notes: Optional booking notes.

    Returns:
        Tuple of (event_id, html_link) or (None, None) if failed.
    """
    if not settings.GOOGLE_CALENDAR_ENABLED:
        return None, None

    try:
        calendar_client = get_calendar_client()
        if not calendar_client:
            return None, None

        start_datetime = format_datetime_iso(booking_date, booking_time)
        end_time = (
            datetime.fromisoformat(f"{booking_date}T{booking_time}:00")
            + timedelta(minutes=duration_minutes)
        ).strftime("%H:%M")
        end_datetime = format_datetime_iso(booking_date, end_time)

        event = calendar_client.create_event(
            summary=f"{service_type} - {customer_name}",
            description=f"Service: {service_type}\nCustomer: {customer_name}\nNotes: {notes}",
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            attendee_email=customer_email,
        )

        logger.info(f"Google Calendar event created: {event.event_id}")
        return event.event_id, event.html_link

    except Exception as exc:
        logger.warning(f"Failed to create Google Calendar event: {exc}")
        return None, None


def update_calendar_event(
    event_id: str,
    new_date: str,
    new_time: str,
    duration_minutes: int,
) -> bool:
    """Update an existing Google Calendar event.

    Args:
        event_id: Google Calendar event ID.
        new_date: New date in YYYY-MM-DD format.
        new_time: New time in HH:MM format.
        duration_minutes: Appointment duration in minutes.

    Returns:
        True if updated successfully, False otherwise.
    """
    try:
        calendar_client = get_calendar_client()
        if not calendar_client:
            return False

        start_datetime = format_datetime_iso(new_date, new_time)
        end_time = (
            datetime.fromisoformat(f"{new_date}T{new_time}:00")
            + timedelta(minutes=duration_minutes)
        ).strftime("%H:%M")
        end_datetime = format_datetime_iso(new_date, end_time)

        calendar_client.update_event(
            event_id=event_id,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
        )

        logger.info(f"Google Calendar event updated: {event_id}")
        return True

    except Exception as exc:
        logger.warning(f"Failed to update calendar event: {exc}")
        return False


def delete_calendar_event(event_id: str, send_notifications: bool = True) -> bool:
    """Delete a Google Calendar event.

    Args:
        event_id: Google Calendar event ID.
        send_notifications: Whether to send cancellation notifications.

    Returns:
        True if deleted successfully, False otherwise.
    """
    try:
        calendar_client = get_calendar_client()
        if not calendar_client:
            return False

        calendar_client.delete_event(event_id, send_notifications=send_notifications)
        logger.info(f"Google Calendar event deleted: {event_id}")
        return True

    except Exception as exc:
        logger.warning(f"Failed to delete calendar event: {exc}")
        return False


def get_calendar_link(event_id: str) -> str | None:
    """Get the HTML link for an existing calendar event.

    Args:
        event_id: Google Calendar event ID.

    Returns:
        HTML link to the event or None if not found.
    """
    try:
        calendar_client = get_calendar_client()
        if not calendar_client:
            return None

        event = calendar_client.get_event(event_id)
        if event:
            return event.html_link
        return None

    except Exception as exc:
        logger.warning(f"Failed to get calendar link: {exc}")
        return None
