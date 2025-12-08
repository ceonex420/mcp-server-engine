"""
MCP Prompt Handlers
AI assistant prompt templates for MCP protocol.
Provides structured prompts for different use cases.
"""

from mcp.server.fastmcp import FastMCP

from utils.logger import get_logger

logger = get_logger("mcp_handlers")

# Global mcp instance - will be injected from server.py
mcp = None


def init_prompt_handlers(mcp_instance: FastMCP) -> None:
    """Initialize prompt handlers with MCP instance."""
    global mcp
    mcp = mcp_instance
    register_prompts()


def register_prompts() -> None:
    """Register all MCP prompts."""

    @mcp.prompt()  # type: ignore[union-attr]
    def search_assistant_prompt(query: str, context: str = "general") -> str:
        """
        Generate a prompt for AI assistants to help users with product searches.

        Args:
            query: User's search query
            context: Search context (general, specific, troubleshooting)

        Returns:
            Formatted prompt for AI assistant
        """
        base_prompt = f"Help the user find products matching: {query}\nContext: {context}"

        if context == "troubleshooting":
            base_prompt += "\nFocus on diagnostic and solution-oriented products."
        elif context == "specific":
            base_prompt += "\nFocus on exact matches and specific product details."

        logger.debug(f"Generated search_assistant_prompt with context={context}")
        return base_prompt

    @mcp.prompt()  # type: ignore[union-attr]
    def product_comparison_prompt(products: list[str]) -> str:
        """
        Generate a prompt for comparing multiple products.

        Args:
            products: List of product identifiers (SKUs or names)

        Returns:
            Formatted prompt for product comparison
        """
        products_str = ", ".join(products)

        comparison_prompt = f"""Product Comparison

Products to compare: {products_str}

Please provide:
1. Key features of each product
2. Price comparison
3. Pros and cons
4. Recommendation based on use case"""

        logger.debug(f"Generated product_comparison_prompt for {len(products)} products")
        return comparison_prompt
