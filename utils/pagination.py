"""Pagination utilities for MCP Server.

Implements standardized pagination patterns following best practices:
- Builder Pattern: PaginationBuilder for constructing paginated queries
- Data Transfer Object: PaginationParams and PaginatedResponse
- Strategy Pattern: Different pagination strategies (offset-based, cursor-based)

Usage:
    from utils.pagination import PaginationParams, PaginatedResponse, paginate

    # Create pagination parameters
    params = PaginationParams(limit=20, offset=0)

    # Validate parameters
    params = params.validate()

    # Build paginated response
    response = PaginatedResponse.create(
        items=results,
        total_count=100,
        params=params
    )

Author: Odiseo Team
Version: 1.0.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from utils.logger import get_logger

logger = get_logger("pagination")

# Type variable for generic paginated response
T = TypeVar("T")


# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================


class PaginationDefaults:
    """Default pagination configuration values."""

    # Default limits by context
    SEARCH_LIMIT = 20
    LIST_LIMIT = 50
    EXPORT_LIMIT = 100

    # Maximum limits (prevents abuse)
    MAX_LIMIT = 100
    ABSOLUTE_MAX_LIMIT = 500  # For admin/export operations

    # Minimum values
    MIN_LIMIT = 1
    MIN_OFFSET = 0


# =============================================================================
# DATA TRANSFER OBJECTS (DTOs)
# =============================================================================


@dataclass(frozen=True)
class PaginationParams:
    """Immutable pagination parameters with validation.

    Implements the Value Object pattern - immutable and validated.

    Attributes:
        limit: Maximum number of items to return.
        offset: Number of items to skip.
        max_limit: Maximum allowed limit (for validation).

    Example:
        >>> params = PaginationParams(limit=20, offset=0)
        >>> validated = params.validate()
        >>> print(validated.limit)  # 20
    """

    limit: int = PaginationDefaults.SEARCH_LIMIT
    offset: int = PaginationDefaults.MIN_OFFSET
    max_limit: int = PaginationDefaults.MAX_LIMIT

    def validate(self) -> PaginationParams:
        """Validate and clamp pagination parameters.

        Returns:
            New PaginationParams with validated values.
        """
        validated_limit = max(PaginationDefaults.MIN_LIMIT, min(self.limit, self.max_limit))
        validated_offset = max(PaginationDefaults.MIN_OFFSET, self.offset)

        if validated_limit != self.limit or validated_offset != self.offset:
            logger.debug(
                f"Pagination params adjusted: limit {self.limit}->{validated_limit}, "
                f"offset {self.offset}->{validated_offset}"
            )

        return PaginationParams(
            limit=validated_limit, offset=validated_offset, max_limit=self.max_limit
        )

    @classmethod
    def for_search(
        cls, limit: int = PaginationDefaults.SEARCH_LIMIT, offset: int = 0
    ) -> PaginationParams:
        """Factory method for search operations."""
        return cls(limit=limit, offset=offset, max_limit=PaginationDefaults.MAX_LIMIT).validate()

    @classmethod
    def for_list(
        cls, limit: int = PaginationDefaults.LIST_LIMIT, offset: int = 0
    ) -> PaginationParams:
        """Factory method for list operations."""
        return cls(limit=limit, offset=offset, max_limit=PaginationDefaults.MAX_LIMIT).validate()

    @classmethod
    def for_export(
        cls, limit: int = PaginationDefaults.EXPORT_LIMIT, offset: int = 0
    ) -> PaginationParams:
        """Factory method for export operations (higher limits)."""
        return cls(
            limit=limit, offset=offset, max_limit=PaginationDefaults.ABSOLUTE_MAX_LIMIT
        ).validate()

    def next_page(self) -> PaginationParams:
        """Get parameters for next page."""
        return PaginationParams(
            limit=self.limit, offset=self.offset + self.limit, max_limit=self.max_limit
        )

    def prev_page(self) -> PaginationParams | None:
        """Get parameters for previous page, or None if at first page."""
        if self.offset <= 0:
            return None
        return PaginationParams(
            limit=self.limit, offset=max(0, self.offset - self.limit), max_limit=self.max_limit
        )


@dataclass
class PaginationMeta:
    """Pagination metadata for responses.

    Provides all necessary information for client-side pagination UI.
    """

    limit: int
    offset: int
    total_count: int
    has_more: bool
    has_previous: bool
    next_offset: int | None
    prev_offset: int | None
    current_page: int
    total_pages: int

    @classmethod
    def create(cls, params: PaginationParams, total_count: int, items_count: int) -> PaginationMeta:
        """Factory method to create pagination metadata.

        Args:
            params: The pagination parameters used.
            total_count: Total number of items in the collection.
            items_count: Number of items in current page.

        Returns:
            PaginationMeta with calculated values.
        """
        has_more = (params.offset + items_count) < total_count
        has_previous = params.offset > 0

        # Calculate page numbers (1-indexed for display)
        current_page = (params.offset // params.limit) + 1 if params.limit > 0 else 1
        total_pages = (
            ((total_count - 1) // params.limit) + 1 if params.limit > 0 and total_count > 0 else 1
        )

        return cls(
            limit=params.limit,
            offset=params.offset,
            total_count=total_count,
            has_more=has_more,
            has_previous=has_previous,
            next_offset=params.offset + params.limit if has_more else None,
            prev_offset=max(0, params.offset - params.limit) if has_previous else None,
            current_page=current_page,
            total_pages=total_pages,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "limit": self.limit,
            "offset": self.offset,
            "total_count": self.total_count,
            "has_more": self.has_more,
            "has_previous": self.has_previous,
            "next_offset": self.next_offset,
            "prev_offset": self.prev_offset,
            "current_page": self.current_page,
            "total_pages": self.total_pages,
        }


@dataclass
class PaginatedResponse(Generic[T]):
    """Generic paginated response container.

    Implements the Data Transfer Object pattern with generic typing.

    Attributes:
        items: List of items in current page.
        count: Number of items in current page.
        total_count: Total number of items across all pages.
        pagination: Pagination metadata.
        extra: Additional context-specific data.

    Example:
        >>> response = PaginatedResponse.create(
        ...     items=[{"id": 1}, {"id": 2}],
        ...     total_count=100,
        ...     params=PaginationParams(limit=2, offset=0)
        ... )
        >>> print(response.pagination.has_more)  # True
    """

    items: list[T]
    count: int
    total_count: int
    pagination: PaginationMeta
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        items: list[T],
        total_count: int,
        params: PaginationParams,
        **extra: Any,
    ) -> PaginatedResponse[T]:
        """Factory method to create a paginated response.

        Args:
            items: Items in current page.
            total_count: Total items across all pages.
            params: Pagination parameters used.
            **extra: Additional context data.

        Returns:
            PaginatedResponse with calculated metadata.
        """
        pagination_meta = PaginationMeta.create(
            params=params, total_count=total_count, items_count=len(items)
        )

        return cls(
            items=items,
            count=len(items),
            total_count=total_count,
            pagination=pagination_meta,
            extra=extra if extra else {},
        )

    @classmethod
    def empty(cls, params: PaginationParams, **extra: Any) -> PaginatedResponse[T]:
        """Create an empty paginated response."""
        return cls.create(items=[], total_count=0, params=params, **extra)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "items": self.items,
            "count": self.count,
            "total_count": self.total_count,
            "pagination": self.pagination.to_dict(),
        }
        if self.extra:
            result.update(self.extra)
        return result
