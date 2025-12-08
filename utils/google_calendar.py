"""Google Calendar API Client.

Provides integration with Google Calendar API using Service Account authentication.
Follows Google's official best practices and python-genai patterns.

Prerequisites:
    - Google Cloud Project with Calendar API enabled
    - Service Account created with Calendar access
    - Service account JSON credentials file
    - Calendar shared with service account email

Environment Variables:
    GOOGLE_CALENDAR_CREDENTIALS_PATH: Path to service account JSON
    GOOGLE_CALENDAR_ID: Target calendar ID

References:
    - https://googleapis.github.io/google-api-python-client/
    - https://developers.google.com/calendar/api/guides/overview
    - https://cloud.google.com/iam/docs/service-accounts

Author: Odiseo Team
Created: 2025-10-11
Version: 1.0.0
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .logger import get_logger  # Proper relative import

# Type variable for retry decorator
T = TypeVar("T")

# Get module logger
logger = get_logger("mcp_google_calendar")

# Google Calendar API settings
SCOPES = ["https://www.googleapis.com/auth/calendar"]
API_SERVICE_NAME = "calendar"
API_VERSION = "v3"


@dataclass
class CalendarEvent:
    """Represents a Google Calendar event.

    Attributes:
        event_id: Google Calendar event ID (unique identifier)
        summary: Event title/name
        description: Event description/notes
        start_datetime: Event start time (ISO 8601)
        end_datetime: Event end time (ISO 8601)
        attendee_email: Attendee email address
        html_link: Public URL to view event
        status: Event status (confirmed, tentative, cancelled)
    """

    event_id: str
    summary: str
    description: str | None
    start_datetime: str
    end_datetime: str
    attendee_email: str | None
    html_link: str
    status: str


class GoogleCalendarError(Exception):
    """Base exception for Google Calendar errors."""


class AuthenticationError(GoogleCalendarError):
    """Raised when service account authentication fails."""


class EventCreationError(GoogleCalendarError):
    """Raised when event creation fails."""


class EventUpdateError(GoogleCalendarError):
    """Raised when event update fails."""


class EventDeletionError(GoogleCalendarError):
    """Raised when event deletion fails."""


def _is_transient_error(http_error: HttpError) -> bool:
    """Check if an HttpError is transient (should be retried).

    Transient errors include:
    - 429: Too Many Requests (rate limiting)
    - 503: Service Unavailable
    - 500: Internal Server Error (occasional)

    Args:
        http_error: HttpError to check

    Returns:
        True if error is transient, False otherwise
    """
    try:
        return http_error.resp.status in (429, 500, 503)
    except (AttributeError, TypeError):
        return False


def _retry_with_backoff(
    func: Callable[..., T],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    exponential_base: float = 2.0,
) -> Callable[..., T]:
    """Wrapper function for retrying with exponential backoff.

    Retries on transient errors (429, 500, 503).

    Args:
        func: Function to wrap
        max_retries: Maximum retry attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 1.0)
        exponential_base: Multiplier for exponential backoff (default: 2.0)

    Returns:
        Wrapped function that retries on transient errors
    """

    def wrapper(*args: Any, **kwargs: Any) -> T:
        delay = initial_delay
        last_error = None

        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except HttpError as e:
                last_error = e
                if not _is_transient_error(e) or attempt == max_retries - 1:
                    raise

                logger.warning(
                    f"Transient error (HTTP {e.resp.status}) on attempt {attempt + 1}/"
                    f"{max_retries}. Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                delay *= exponential_base

        # This should never happen, but just in case
        raise last_error or RuntimeError("Retry exhausted without error")

    return wrapper


class GoogleCalendarClient:
    """Google Calendar API client using Service Account authentication.

    This class provides a clean interface to Google Calendar API for managing
    events (create, read, update, delete) with proper error handling and logging.

    Example:
        >>> client = GoogleCalendarClient(
        ...     credentials_path="credentials/service-account.json",
        ...     calendar_id="primary"
        ... )
        >>> event = client.create_event(
        ...     summary="Client Meeting",
        ...     description="Discuss project requirements",
        ...     start_datetime="2025-10-12T15:00:00-05:00",
        ...     end_datetime="2025-10-12T16:00:00-05:00",
        ...     attendee_email="client@example.com"
        ... )
        >>> print(f"Event created: {event.html_link}")
    """

    def __init__(
        self,
        credentials_path: str | Path,
        calendar_id: str = "primary",
        *,
        timezone: str = "America/New_York",
    ) -> None:
        """Initialize Google Calendar client.

        Args:
            credentials_path: Path to service account JSON credentials file.
            calendar_id: Target calendar ID (default: "primary").
                        Can be email address or calendar identifier.
            timezone: Default timezone for events (default: America/New_York).

        Raises:
            AuthenticationError: If service account authentication fails.
            FileNotFoundError: If credentials file not found.
        """
        self.credentials_path = Path(credentials_path)
        self.calendar_id = calendar_id
        self.timezone = timezone
        self._service: Any | None = None
        self._credentials: service_account.Credentials | None = None

        logger.info(f"Initializing Google Calendar client for calendar: {calendar_id}")
        self._authenticate()

    def _authenticate(self) -> None:
        """Authenticate with Google Calendar API using service account.

        Raises:
            AuthenticationError: If authentication fails.
            FileNotFoundError: If credentials file not found.
        """
        try:
            if not self.credentials_path.exists():
                raise FileNotFoundError(
                    f"Google Calendar credentials file not found: {self.credentials_path}"
                )

            logger.debug(f"Loading credentials from: {self.credentials_path}")

            # Load service account credentials
            self._credentials = service_account.Credentials.from_service_account_file(
                str(self.credentials_path),
                scopes=SCOPES,
            )

            # Build Calendar API service
            self._service = build(
                API_SERVICE_NAME,
                API_VERSION,
                credentials=self._credentials,
                cache_discovery=False,  # Disable discovery cache for production
            )

            logger.info("Google Calendar authentication successful")

        except FileNotFoundError:
            logger.error(f"Credentials file not found: {self.credentials_path}")
            raise

        except Exception as exc:
            logger.exception(f"Authentication failed: {exc}")
            raise AuthenticationError(f"Google Calendar authentication failed: {exc}") from exc

    def _refresh_credentials_if_needed(self) -> None:
        """Refresh credentials if expired.

        Raises:
            AuthenticationError: If credential refresh fails.
        """
        if not self._credentials:
            raise AuthenticationError("Google Calendar credentials not initialized")

        try:
            if self._credentials.expired:
                logger.debug("Refreshing expired credentials...")
                self._credentials.refresh(Request())
                logger.debug("Credentials refreshed successfully")
        except Exception as exc:
            logger.exception(f"Failed to refresh credentials: {exc}")
            raise AuthenticationError(f"Failed to refresh credentials: {exc}") from exc

    def create_event(
        self,
        summary: str,
        description: str,
        start_datetime: str,
        end_datetime: str,
        attendee_email: str | None = None,
        *,
        send_notifications: bool = True,
    ) -> CalendarEvent:
        """Create a new calendar event.

        Args:
            summary: Event title/name.
            description: Event description/notes.
            start_datetime: Start time in ISO 8601 format (e.g., "2025-10-12T15:00:00-05:00").
            end_datetime: End time in ISO 8601 format.
            attendee_email: Optional attendee email address.
            send_notifications: Whether to send email notifications (default: True).

        Returns:
            CalendarEvent object with event details.

        Raises:
            EventCreationError: If event creation fails.

        Example:
            >>> event = client.create_event(
            ...     summary="Team Meeting",
            ...     description="Weekly sync",
            ...     start_datetime="2025-10-12T10:00:00-05:00",
            ...     end_datetime="2025-10-12T11:00:00-05:00",
            ...     attendee_email="team@example.com"
            ... )
        """
        if not self._service:
            raise AuthenticationError("Google Calendar service not initialized")

        try:
            self._refresh_credentials_if_needed()

            # Build event body
            event_body: dict[str, Any] = {
                "summary": summary,
                "description": description,
                "start": {
                    "dateTime": start_datetime,
                    "timeZone": self.timezone,
                },
                "end": {
                    "dateTime": end_datetime,
                    "timeZone": self.timezone,
                },
            }

            # Add attendee if provided
            # Best-effort approach: Try to add as attendee, fall back to description
            if attendee_email:
                try:
                    # Try to add attendee (requires Domain-Wide Delegation for service accounts)
                    event_body["attendees"] = [{"email": attendee_email}]
                    logger.debug(f"Added attendee: {attendee_email}")
                except Exception as e:
                    # If attendee addition fails, fall back to adding email to description
                    logger.warning(f"Failed to add attendee {attendee_email}: {e}")
                    event_body["description"] += f"\n\nCustomer Email: {attendee_email}"

            # Add reminders (30 min and 10 min before)
            event_body["reminders"] = {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 30},
                    {"method": "popup", "minutes": 10},
                ],
            }

            logger.info(f"Creating event: {summary} at {start_datetime}")
            logger.debug(f"Event body: {event_body}")

            # Create event with retry logic for transient errors
            def _create_event_with_retry() -> dict[str, Any]:
                return (
                    self._service.events()
                    .insert(
                        calendarId=self.calendar_id,
                        body=event_body,
                        sendNotifications=send_notifications,
                    )
                    .execute()
                )

            try:
                # Try to create with attendee first
                created_event = _retry_with_backoff(
                    _create_event_with_retry,
                    max_retries=3,
                    initial_delay=1.0,
                    exponential_base=2.0,
                )()
            except HttpError as exc:
                # If creation failed with 403 (permission denied) and we have an attendee,
                # try again without the attendee and add to description instead
                if exc.resp.status == 403 and attendee_email and "attendees" in event_body:
                    logger.warning("Permission denied for attendees, retrying without")
                    # Remove attendee and add to description instead
                    del event_body["attendees"]
                    event_body["description"] += f"\n\nCustomer Email: {attendee_email}"

                    try:
                        created_event = _retry_with_backoff(
                            _create_event_with_retry,
                            max_retries=3,
                            initial_delay=1.0,
                            exponential_base=2.0,
                        )()
                    except HttpError as retry_exc:
                        logger.exception(f"HTTP error creating event (retry): {retry_exc}")
                        raise EventCreationError(
                            f"Failed to create event after retry: {retry_exc}"
                        ) from retry_exc
                else:
                    logger.exception(f"HTTP error creating event: {exc}")
                    raise EventCreationError(f"Failed to create event: {exc}") from exc

            logger.info(f"Event created successfully: {created_event['id']}")
            logger.debug(f"Event link: {created_event.get('htmlLink')}")

            return self._parse_event(created_event)

        except Exception as exc:
            logger.exception(f"Unexpected error creating event: {exc}")
            raise EventCreationError(f"Failed to create event: {exc}") from exc

    def update_event(
        self,
        event_id: str,
        *,
        summary: str | None = None,
        description: str | None = None,
        start_datetime: str | None = None,
        end_datetime: str | None = None,
        send_notifications: bool = True,
    ) -> CalendarEvent:
        """Update an existing calendar event.

        Args:
            event_id: Google Calendar event ID to update.
            summary: New event title (optional).
            description: New event description (optional).
            start_datetime: New start time in ISO 8601 format (optional).
            end_datetime: New end time in ISO 8601 format (optional).
            send_notifications: Whether to send email notifications (default: True).

        Returns:
            Updated CalendarEvent object.

        Raises:
            EventUpdateError: If event update fails.

        Example:
            >>> updated = client.update_event(
            ...     event_id="abc123",
            ...     start_datetime="2025-10-13T10:00:00-05:00",
            ...     end_datetime="2025-10-13T11:00:00-05:00"
            ... )
        """
        if not self._service:
            raise AuthenticationError("Google Calendar service not initialized")

        try:
            self._refresh_credentials_if_needed()

            # Fetch existing event
            logger.info(f"Fetching event to update: {event_id}")
            existing_event = (
                self._service.events().get(calendarId=self.calendar_id, eventId=event_id).execute()
            )

            # Update fields
            if summary is not None:
                existing_event["summary"] = summary

            if description is not None:
                existing_event["description"] = description

            if start_datetime is not None:
                existing_event["start"] = {
                    "dateTime": start_datetime,
                    "timeZone": self.timezone,
                }

            if end_datetime is not None:
                existing_event["end"] = {
                    "dateTime": end_datetime,
                    "timeZone": self.timezone,
                }

            logger.info(f"Updating event: {event_id}")
            logger.debug(f"Updated fields: summary={summary}, start={start_datetime}")

            # Update event with retry logic for transient errors
            def _update_event_with_retry() -> dict[str, Any]:
                return (
                    self._service.events()
                    .update(
                        calendarId=self.calendar_id,
                        eventId=event_id,
                        body=existing_event,
                        sendNotifications=send_notifications,
                    )
                    .execute()
                )

            updated_event = _retry_with_backoff(
                _update_event_with_retry,
                max_retries=3,
                initial_delay=1.0,
                exponential_base=2.0,
            )()

            logger.info(f"Event updated successfully: {event_id}")
            return self._parse_event(updated_event)

        except HttpError as exc:
            logger.exception(f"HTTP error updating event: {exc}")
            raise EventUpdateError(f"Failed to update event {event_id}: {exc}") from exc

        except Exception as exc:
            logger.exception(f"Unexpected error updating event: {exc}")
            raise EventUpdateError(f"Failed to update event {event_id}: {exc}") from exc

    def delete_event(
        self,
        event_id: str,
        *,
        send_notifications: bool = True,
    ) -> bool:
        """Delete a calendar event.

        Args:
            event_id: Google Calendar event ID to delete.
            send_notifications: Whether to send cancellation notifications (default: True).

        Returns:
            True if deletion successful.

        Raises:
            EventDeletionError: If event deletion fails.

        Example:
            >>> success = client.delete_event("abc123")
            >>> assert success is True
        """
        if not self._service:
            raise AuthenticationError("Google Calendar service not initialized")

        try:
            self._refresh_credentials_if_needed()

            logger.info(f"Deleting event: {event_id}")

            self._service.events().delete(
                calendarId=self.calendar_id,
                eventId=event_id,
                sendNotifications=send_notifications,
            ).execute()

            logger.info(f"Event deleted successfully: {event_id}")
            return True

        except HttpError as exc:
            logger.exception(f"HTTP error deleting event: {exc}")
            raise EventDeletionError(f"Failed to delete event {event_id}: {exc}") from exc

        except Exception as exc:
            logger.exception(f"Unexpected error deleting event: {exc}")
            raise EventDeletionError(f"Failed to delete event {event_id}: {exc}") from exc

    def get_event(self, event_id: str) -> CalendarEvent:
        """Retrieve event details by ID.

        Args:
            event_id: Google Calendar event ID.

        Returns:
            CalendarEvent object with event details.

        Raises:
            GoogleCalendarError: If event retrieval fails.
        """
        if not self._service:
            raise AuthenticationError("Google Calendar service not initialized")

        try:
            self._refresh_credentials_if_needed()

            logger.debug(f"Fetching event: {event_id}")

            event = (
                self._service.events().get(calendarId=self.calendar_id, eventId=event_id).execute()
            )

            return self._parse_event(event)

        except HttpError as exc:
            logger.exception(f"HTTP error fetching event: {exc}")
            raise GoogleCalendarError(f"Failed to fetch event {event_id}: {exc}") from exc

        except Exception as exc:
            logger.exception(f"Unexpected error fetching event: {exc}")
            raise GoogleCalendarError(f"Failed to fetch event {event_id}: {exc}") from exc

    def get_busy_times(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, str]]:
        """Get busy time slots within a date range.

        Useful for checking availability before booking.

        Args:
            start_date: Range start datetime.
            end_date: Range end datetime.

        Returns:
            List of busy time slots as dicts with 'start' and 'end' keys.

        Raises:
            GoogleCalendarError: If busy time query fails.

        Example:
            >>> from datetime import datetime, timedelta
            >>> start = datetime.now()
            >>> end = start + timedelta(days=7)
            >>> busy_times = client.get_busy_times(start, end)
            >>> for slot in busy_times:
            ...     print(f"{slot['start']} - {slot['end']}")
        """
        if not self._service:
            raise AuthenticationError("Google Calendar service not initialized")

        try:
            self._refresh_credentials_if_needed()

            logger.debug(f"Querying busy times: {start_date} to {end_date}")

            # FreeBusy query body
            body = {
                "timeMin": start_date.isoformat(),
                "timeMax": end_date.isoformat(),
                "timeZone": self.timezone,
                "items": [{"id": self.calendar_id}],
            }

            response = self._service.freebusy().query(body=body).execute()

            busy_times = response.get("calendars", {}).get(self.calendar_id, {}).get("busy", [])

            logger.debug(f"Found {len(busy_times)} busy time slots")
            return busy_times

        except HttpError as exc:
            logger.exception(f"HTTP error querying busy times: {exc}")
            raise GoogleCalendarError(f"Failed to query busy times: {exc}") from exc

        except Exception as exc:
            logger.exception(f"Unexpected error querying busy times: {exc}")
            raise GoogleCalendarError(f"Failed to query busy times: {exc}") from exc

    def _parse_event(self, event_data: dict[str, Any]) -> CalendarEvent:
        """Parse Google Calendar API event response into CalendarEvent.

        Args:
            event_data: Raw event data from Google Calendar API.

        Returns:
            CalendarEvent object.
        """
        # Extract attendee email if present
        attendees = event_data.get("attendees", [])
        attendee_email = attendees[0]["email"] if attendees else None

        return CalendarEvent(
            event_id=event_data["id"],
            summary=event_data.get("summary", ""),
            description=event_data.get("description"),
            start_datetime=event_data["start"]["dateTime"],
            end_datetime=event_data["end"]["dateTime"],
            attendee_email=attendee_email,
            html_link=event_data.get("htmlLink", ""),
            status=event_data.get("status", "confirmed"),
        )

    def __repr__(self) -> str:
        """String representation of GoogleCalendarClient."""
        return f"GoogleCalendarClient(calendar_id={self.calendar_id}, timezone={self.timezone})"
