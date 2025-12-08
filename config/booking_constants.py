"""Booking System Constants and Enumerations.

This module consolidates all booking-related constants, enums, and status
values that were previously hardcoded in various modules. Centralizing these
improves maintainability and allows for configuration-driven customization.

References:
    - SQL/scripts/create_bookings_schema.sql (database schema)
    - mcp_server/tools/bookings.py (business logic)
    - mcp_server/mcp_handlers/booking_handlers.py (MCP handlers)

Author: Odiseo Team
Created: 2025-10-16
Version: 1.0.0
"""

from enum import Enum


class BookingStatus(str, Enum):
    """Booking status enumeration.

    Represents the lifecycle states of a booking/appointment.
    Maps to database `status` column in appointments table.
    """

    CONFIRMED = "confirmed"
    """Booking is confirmed and active."""

    CANCELLED = "cancelled"
    """Booking has been cancelled by customer or system."""

    RESCHEDULED = "rescheduled"
    """Booking has been rescheduled to a different date/time."""

    COMPLETED = "completed"
    """Booking has been completed (appointment occurred)."""

    NO_SHOW = "no_show"
    """Customer did not show up for booking."""

    @classmethod
    def active_statuses(cls) -> set["BookingStatus"]:
        """Get all active booking statuses (not cancelled/completed)."""
        return {cls.CONFIRMED, cls.RESCHEDULED}

    @classmethod
    def non_reschedulable(cls) -> set["BookingStatus"]:
        """Get statuses that cannot be rescheduled."""
        return {cls.CANCELLED, cls.COMPLETED}


class EmailNotificationType(str, Enum):
    """Email notification types for booking events.

    Maps to email queue system notification types.
    """

    BOOKING_CREATED = "booking_created"
    """Notification for new booking creation."""

    BOOKING_CANCELLED = "booking_cancelled"
    """Notification for booking cancellation."""

    BOOKING_RESCHEDULED = "booking_rescheduled"
    """Notification for booking reschedule."""


# Default values for booking system
BOOKING_DEFAULTS = {
    "default_status": BookingStatus.CONFIRMED,
    "default_duration_minutes": 60,
    "default_email_priority": 5,
    "email_queue_priority": 5,
}


# Status transition rules
VALID_STATUS_TRANSITIONS = {
    BookingStatus.CONFIRMED: {
        BookingStatus.RESCHEDULED,
        BookingStatus.CANCELLED,
        BookingStatus.COMPLETED,
    },
    BookingStatus.RESCHEDULED: {BookingStatus.CANCELLED, BookingStatus.COMPLETED},
    BookingStatus.CANCELLED: set(),  # Terminal state
    BookingStatus.COMPLETED: set(),  # Terminal state
    BookingStatus.NO_SHOW: set(),  # Terminal state
}


__all__ = [
    "BOOKING_DEFAULTS",
    "VALID_STATUS_TRANSITIONS",
    "BookingStatus",
    "EmailNotificationType",
]
