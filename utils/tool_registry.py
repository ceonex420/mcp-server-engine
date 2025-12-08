"""
Tool Registry - Dynamic Tool Discovery without Hardcoding.

This module provides a mechanism for handlers to dynamically track and discover
registered tools without hardcoding tool lists. Each handler registers tools
and the registry automatically tracks them.

Benefits:
- No hardcoded tool lists (get_*_tool_names becomes dynamic)
- Single source of truth: the tool decorator itself
- Automatic discovery when new tools are added
- Type-safe and maintainable

Usage:
    from utils.tool_registry import ToolRegistry

    # In handler module
    tool_registry = ToolRegistry()

    @mcp.tool()
    def my_tool():
        '''Tool description'''
        pass

    # Register it
    tool_registry.register_tool("my_tool", category="booking")

    # Later, discover all booking tools
    booking_tools = tool_registry.get_tools_by_category("booking")

Author: Odiseo Team
Version: 1.0.0
"""

from __future__ import annotations


class ToolRegistry:
    """
    Dynamic tool registry for tracking registered tools by category.

    Replaces hardcoded tool lists with dynamic discovery.
    """

    def __init__(self):
        """Initialize the tool registry."""
        # Structure: {"category": ["tool1", "tool2"], ...}
        self._tools_by_category: dict[str, list[str]] = {}
        # Structure: {"tool_name": "category", ...}
        self._tool_to_category: dict[str, str] = {}

    def register_tool(self, tool_name: str, category: str) -> None:
        """
        Register a tool in a category.

        Args:
            tool_name: Name of the tool (must match MCP tool name)
            category: Category the tool belongs to (e.g., "booking", "product")
        """
        # Add to category list
        if category not in self._tools_by_category:
            self._tools_by_category[category] = []

        if tool_name not in self._tools_by_category[category]:
            self._tools_by_category[category].append(tool_name)

        # Add to lookup map
        self._tool_to_category[tool_name] = category

    def register_tools(self, tool_names: list[str], category: str) -> None:
        """
        Register multiple tools in a category.

        Args:
            tool_names: List of tool names
            category: Category for all tools
        """
        for tool_name in tool_names:
            self.register_tool(tool_name, category)

    def get_tools_by_category(self, category: str) -> list[str]:
        """
        Get all tools in a category.

        Args:
            category: Category name

        Returns:
            List of tool names in this category
        """
        return self._tools_by_category.get(category, [])

    def get_tool_category(self, tool_name: str) -> str | None:
        """
        Get the category of a specific tool.

        Args:
            tool_name: Tool name

        Returns:
            Category name or None if not found
        """
        return self._tool_to_category.get(tool_name)

    def get_all_categories(self) -> list[str]:
        """
        Get all registered categories.

        Returns:
            List of category names
        """
        return list(self._tools_by_category.keys())

    def get_all_tools(self) -> dict[str, list[str]]:
        """
        Get all tools organized by category.

        Returns:
            Dict mapping category -> list of tool names
        """
        return dict(self._tools_by_category)

    def __repr__(self) -> str:
        """String representation of registry."""
        summary = {}
        for category, tools in self._tools_by_category.items():
            summary[category] = len(tools)
        return f"ToolRegistry({summary})"
