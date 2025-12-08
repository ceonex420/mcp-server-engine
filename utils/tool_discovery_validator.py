"""
Tool Discovery Validator - Validates that tool registries are properly populated.

This module provides validation functions to ensure:
1. All tools that are @mcp.tool() decorated are registered in a registry
2. No tools are missing from categories
3. Tool names match between registration and MCP definitions
4. Registry consistency and integrity

Usage:
    from utils.tool_discovery_validator import validate_tool_registries

    # After handlers are initialized
    validation_result = validate_tool_registries(mcp_instance)
    if validation_result.is_valid:
        print("✅ All tool registries are valid!")
    else:
        print(f"❌ Validation errors: {validation_result.errors}")

Author: Odiseo Team
Version: 1.0.0
"""

from __future__ import annotations

from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from utils.logger import get_logger

logger = get_logger("mcp_handlers")


@dataclass
class ValidationResult:
    """Result of tool registry validation."""

    is_valid: bool
    total_tools: int
    total_categories: int
    tools_by_category: dict[str, list[str]]
    errors: list[str]
    warnings: list[str]

    def __str__(self) -> str:
        """String representation of validation result."""
        status = "✅ VALID" if self.is_valid else "❌ INVALID"
        lines = [
            f"{status}",
            f"  Total tools: {self.total_tools}",
            f"  Total categories: {self.total_categories}",
        ]

        for category, tools in sorted(self.tools_by_category.items()):
            lines.append(f"  {category}: {len(tools)} tools")

        if self.errors:
            lines.append("\n❌ ERRORS:")
            for error in self.errors:
                lines.append(f"    - {error}")

        if self.warnings:
            lines.append("\n⚠️  WARNINGS:")
            for warning in self.warnings:
                lines.append(f"    - {warning}")

        return "\n".join(lines)


def validate_tool_registries(
    mcp: FastMCP,
    booking_registry: object | None = None,
    sales_registry: object | None = None,
    pageable_registry: object | None = None,
) -> ValidationResult:
    """
    Validate that tool registries are properly populated.

    Args:
        mcp: FastMCP server instance to inspect
        booking_registry: Booking tool registry instance
        sales_registry: Sales tool registry instance
        pageable_registry: Pageable tool registry instance

    Returns:
        ValidationResult with detailed validation information
    """
    errors = []
    warnings = []
    tools_by_category = {}

    # Get all tools from MCP server
    if not hasattr(mcp, "_tool_manager"):
        errors.append("FastMCP does not have _tool_manager attribute")
        return ValidationResult(
            is_valid=False,
            total_tools=0,
            total_categories=0,
            tools_by_category={},
            errors=errors,
            warnings=warnings,
        )

    mcp_tools = mcp._tool_manager._tools
    mcp_tool_names = set(mcp_tools.keys())

    logger.info(f"Found {len(mcp_tool_names)} tools registered in MCP server")

    # Validate booking registry
    if booking_registry and hasattr(booking_registry, "get_all_tools"):
        booking_tools_by_cat = booking_registry.get_all_tools()
        tools_by_category.update(booking_tools_by_cat)

        for tools in booking_tools_by_cat.values():
            for tool_name in tools:
                if tool_name not in mcp_tool_names:
                    errors.append(f"Booking registry tool '{tool_name}' not found in MCP server")
                else:
                    logger.debug(f"Tool '{tool_name}' verified in booking registry")

    # Validate sales registry
    if sales_registry and hasattr(sales_registry, "get_all_tools"):
        sales_tools_by_cat = sales_registry.get_all_tools()
        tools_by_category.update(sales_tools_by_cat)

        for tools in sales_tools_by_cat.values():
            for tool_name in tools:
                if tool_name not in mcp_tool_names:
                    errors.append(f"Sales registry tool '{tool_name}' not found in MCP server")
                else:
                    logger.debug(f"Tool '{tool_name}' verified in sales registry")

    # Validate pageable registry
    if pageable_registry and hasattr(pageable_registry, "get_all_tools"):
        pageable_tools_by_cat = pageable_registry.get_all_tools()
        tools_by_category.update(pageable_tools_by_cat)

        for tools in pageable_tools_by_cat.values():
            for tool_name in tools:
                if tool_name not in mcp_tool_names:
                    errors.append(f"Pageable registry tool '{tool_name}' not found in MCP server")
                else:
                    logger.debug(f"Tool '{tool_name}' verified in pageable registry")

    # Check for unregistered tools
    registered_tool_names = set()
    for tools in tools_by_category.values():
        registered_tool_names.update(tools)

    unregistered_tools = mcp_tool_names - registered_tool_names
    if unregistered_tools:
        warnings.append(
            f"Found {len(unregistered_tools)} tools not in any registry: {sorted(unregistered_tools)}"
        )

    # Summary
    total_tools = len(registered_tool_names)
    total_categories = len(tools_by_category)
    is_valid = len(errors) == 0

    result = ValidationResult(
        is_valid=is_valid,
        total_tools=total_tools,
        total_categories=total_categories,
        tools_by_category=tools_by_category,
        errors=errors,
        warnings=warnings,
    )

    logger.info(f"Tool registry validation: {result}")

    return result


def log_tool_discovery_status(validation_result: ValidationResult) -> None:
    """
    Log tool discovery status in a human-readable format.

    Args:
        validation_result: ValidationResult from validate_tool_registries()
    """
    if validation_result.is_valid:
        logger.info("Tool discovery system is READY FOR PRODUCTION")
        logger.info(f"   - {validation_result.total_tools} tools registered")
        logger.info(f"   - {validation_result.total_categories} categories configured")

        # Log tools per category
        for category, tools in sorted(validation_result.tools_by_category.items()):
            logger.info(f"   - {category}: {len(tools)} tools")
    else:
        logger.error("Tool discovery validation FAILED")
        for error in validation_result.errors:
            logger.error(f"   ERROR: {error}")

    if validation_result.warnings:
        for warning in validation_result.warnings:
            logger.warning(f"   WARNING: {warning}")
