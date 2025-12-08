"""Booking management module for MCP server.

Provides business logic functions for managing appointments/reservations:
- Create, cancel, reschedule bookings
- Check availability
- Fetch booking details
- Google Calendar integration

All operations are async for non-blocking database access.

Author: Odiseo Team
Version: 2.0.0
"""

from .availability import (
    find_first_available_slots_in_range_async,
    get_available_slots_async,
)
from .core import (
    cancel_booking_async,
    create_booking_async,
    reschedule_booking_async,
)
from .queries import (
    get_booking_by_id_async,
    get_business_hours_async,
    get_services_async,
    list_customer_bookings_async,
)

__all__ = [
    "cancel_booking_async",
    "create_booking_async",
    "find_first_available_slots_in_range_async",
    "get_available_slots_async",
    "get_booking_by_id_async",
    "get_business_hours_async",
    "get_services_async",
    "list_customer_bookings_async",
    "reschedule_booking_async",
]
