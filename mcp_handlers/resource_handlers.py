"""
MCP Resource Handlers
Resource endpoints for MCP protocol.
Provides URI-based access to data resources.

Follows MCP Best Practices:
- Async handlers for non-blocking I/O
- MIME types declared for proper content handling
- Structured JSON error responses

Note: MCP resources MUST always return valid JSON responses, even on errors.
Therefore, broad exception catching with structured error responses is intentional.
"""

import json

import asyncpg
from mcp.server.fastmcp import FastMCP

from config import settings
from mcp_handlers import booking_handlers, otp_handler, sales_handlers
from tools.sales import fetch_by_sku_async
from utils.db_async import fetchone_async
from utils.logger import get_logger
from utils.validation import validate_schema_name

logger = get_logger("mcp_handlers")

# Global mcp instance - will be injected from server.py
mcp = None


def init_resource_handlers(mcp_instance: FastMCP) -> None:
    """Initialize resource handlers with MCP instance."""
    global mcp
    mcp = mcp_instance
    register_resources()


def register_resources() -> None:
    """Register all MCP resources."""

    @mcp.resource("product://sku/{sku}", mime_type="application/json")  # type: ignore[union-attr]
    async def get_product_by_sku(sku: str) -> str:
        """
        Resource to access product data by SKU.

        Args:
            sku: Product SKU identifier

        Returns:
            Product information as JSON
        """
        try:
            product = await fetch_by_sku_async(sku)
            if product:
                # Convert Decimal to string for JSON serialization
                price = product.get("price", "N/A")
                if hasattr(price, "__float__"):
                    price = str(price)
                return json.dumps(
                    {
                        "success": True,
                        "data": {
                            "name": product.get("name", "N/A"),
                            "sku": product.get("sku", "N/A"),
                            "description": product.get("description", "N/A"),
                            "category": product.get("category", "N/A"),
                            "brand": product.get("brand", "N/A"),
                            "price": price,
                            "image_url": product.get("image_url"),
                        },
                    }
                )
            return json.dumps(
                {
                    "success": False,
                    "error": {"code": "PRODUCT_NOT_FOUND", "message": f"Product not found: {sku}"},
                }
            )
        except asyncpg.PostgresError as e:
            logger.error(f"Database error retrieving product {sku}: {e!s}")
            return json.dumps(
                {
                    "success": False,
                    "error": {
                        "code": "DATABASE_ERROR",
                        "message": f"Database error retrieving product {sku}",
                        "details": str(e),
                    },
                }
            )
        except Exception as e:
            logger.error(f"Error retrieving product {sku}: {e!s}")
            return json.dumps(
                {
                    "success": False,
                    "error": {
                        "code": "RETRIEVAL_ERROR",
                        "message": f"Error retrieving product {sku}",
                        "details": str(e),
                    },
                }
            )

    @mcp.resource("database://stats", mime_type="application/json")  # type: ignore[union-attr]
    async def get_database_stats() -> str:
        """
        Resource providing database statistics.

        Returns:
            Database statistics as JSON
        """
        try:
            # Validate schema name to prevent SQL injection
            validate_schema_name(settings.SCHEMA_NAME)

            stats_query = f"""
            SELECT
                COUNT(*) as total_products,
                COUNT(DISTINCT category) as categories,
                COUNT(DISTINCT brand) as brands,
                AVG(price) as avg_price
            FROM {settings.SCHEMA_NAME}.products
            """
            result = await fetchone_async(stats_query)
            if result:
                return json.dumps(
                    {
                        "success": True,
                        "data": {
                            "total_products": result.get("total_products", 0),
                            "categories": result.get("categories", 0),
                            "brands": result.get("brands", 0),
                            "avg_price": round(float(result.get("avg_price", 0)), 2),
                            "schema": settings.SCHEMA_NAME,
                        },
                    }
                )
            return json.dumps(
                {
                    "success": False,
                    "error": {
                        "code": "NO_DATA",
                        "message": "Unable to retrieve database statistics",
                    },
                }
            )
        except ValueError as e:
            logger.error(f"Validation error in database stats: {e!s}")
            return json.dumps(
                {
                    "success": False,
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Invalid schema configuration",
                        "details": str(e),
                    },
                }
            )
        except asyncpg.PostgresError as e:
            logger.error(f"Database error retrieving stats: {e!s}")
            return json.dumps(
                {
                    "success": False,
                    "error": {
                        "code": "DATABASE_ERROR",
                        "message": "Database error retrieving stats",
                        "details": str(e),
                    },
                }
            )
        except Exception as e:
            logger.error(f"Error retrieving database stats: {e!s}")
            return json.dumps(
                {
                    "success": False,
                    "error": {
                        "code": "STATS_ERROR",
                        "message": "Error retrieving database stats",
                        "details": str(e),
                    },
                }
            )

    @mcp.resource("tool-categories://sales", mime_type="application/json")  # type: ignore[union-attr]
    async def get_sales_tool_categories() -> str:
        """
        Resource providing list of sales tool names for dynamic filtering.

        This resource enables clients to dynamically discover which tools belong
        to the sales category without hardcoding tool lists in client code.

        Returns:
            JSON string containing list of sales tool names
        """
        try:
            tool_names = sales_handlers.get_sales_tool_names()
            return json.dumps(
                {
                    "success": True,
                    "data": {"category": "sales", "tools": tool_names, "count": len(tool_names)},
                }
            )
        except Exception as e:
            return json.dumps(
                {
                    "success": False,
                    "error": {
                        "code": "DISCOVERY_ERROR",
                        "message": f"Error retrieving sales tool names: {e!s}",
                    },
                }
            )

    @mcp.resource("tool-categories://bookings", mime_type="application/json")  # type: ignore[union-attr]
    async def get_booking_tool_categories() -> str:
        """
        Resource providing list of booking tool names for dynamic filtering.

        This resource enables clients to dynamically discover which tools belong
        to the booking category without hardcoding tool lists in client code.

        Returns:
            JSON string containing list of booking tool names
        """
        try:
            tool_names = booking_handlers.get_booking_tool_names()
            return json.dumps(
                {
                    "success": True,
                    "data": {"category": "bookings", "tools": tool_names, "count": len(tool_names)},
                }
            )
        except Exception as e:
            return json.dumps(
                {
                    "success": False,
                    "error": {
                        "code": "DISCOVERY_ERROR",
                        "message": f"Error retrieving booking tool names: {e!s}",
                    },
                }
            )

    @mcp.resource("tool-categories://pageable-tools", mime_type="application/json")  # type: ignore[union-attr]
    async def get_pageable_tool_categories() -> str:
        """
        Resource providing list of tools that return pageable result lists.

        This resource enables clients to dynamically discover which tools return
        pageable lists for implementing client-side pagination. This eliminates
        the need for hardcoding tool lists (like SEARCH_TOOL_NAMES) in client code.

        Pageable tools return results in formats like:
        - {"items": [...], "count": N}  (most common)
        - list directly (fallback)

        Returns:
            JSON string containing list of pageable tool names
        """
        try:
            tool_names = sales_handlers.get_pageable_tool_names()
            return json.dumps(
                {
                    "success": True,
                    "data": {
                        "category": "pageable",
                        "tools": tool_names,
                        "count": len(tool_names),
                        "description": "Tools that return pageable result lists",
                    },
                }
            )
        except Exception as e:
            return json.dumps(
                {
                    "success": False,
                    "error": {
                        "code": "DISCOVERY_ERROR",
                        "message": f"Error retrieving pageable tool names: {e!s}",
                    },
                }
            )

    @mcp.resource("tool-categories://otp", mime_type="application/json")  # type: ignore[union-attr]
    async def get_otp_tool_categories() -> str:
        """
        Resource providing list of OTP tool names for dynamic filtering.

        This resource enables clients to dynamically discover which tools belong
        to the OTP category without hardcoding tool lists in client code.

        Returns:
            JSON string containing list of OTP tool names
        """
        try:
            tool_names = otp_handler.get_otp_tool_names()
            return json.dumps(
                {
                    "success": True,
                    "data": {
                        "category": "otp",
                        "tools": tool_names,
                        "count": len(tool_names),
                    },
                }
            )
        except Exception as e:
            return json.dumps(
                {
                    "success": False,
                    "error": {
                        "code": "DISCOVERY_ERROR",
                        "message": f"Error retrieving OTP tool names: {e!s}",
                    },
                }
            )
