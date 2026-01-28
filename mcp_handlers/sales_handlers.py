"""
Sales MCP Tool Handlers.

Async wrappers for product/sales MCP tools with Context support.
Separates MCP protocol handling from business logic.

This module provides MCP tool decorators for product search functionality:
- Semantic search using AI embeddings (Gemini)
- Fuzzy text search with typo tolerance
- Direct SKU/ID lookups
"""

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

# Async versions for non-blocking I/O
from tools.sales import (
    fetch_by_id_async,
    fetch_by_sku_async,
    fuzzy_search_smart_async,
    search_products_async,
    search_products_by_embedding_async,
)
from tools.sales.bant_analyzer import analyze_lead_bant_async
from utils.concurrency import ConcurrencyLimitExceeded, acquire_slot
from utils.logger import get_logger
from utils.rate_limiter import RateLimiter
from utils.tool_registry import ToolRegistry

# Get logger for sales handlers
logger = get_logger("mcp_handlers")

# Rate limiter for search operations (MCP Best Practice)
# 30 searches per minute per session (prevents abuse)
search_limiter = RateLimiter(max_calls=30, period_seconds=60)

# Global mcp instance - injected from server.py during initialization
# Note: This pattern is thread-safe because:
# 1. init_product_handlers() is called once during server startup (before any requests)
# 2. FastMCP handles all request routing after initialization
# 3. The mcp instance is read-only after initialization
mcp = None

# Dynamic tool registries - tracks tools as they're registered (no hardcoding!)
sales_tool_registry = ToolRegistry()
pageable_tool_registry = ToolRegistry()


def init_sales_handlers(mcp_instance: FastMCP) -> None:
    """Initialize sales handlers with MCP instance."""
    global mcp
    mcp = mcp_instance
    register_tools()
    logger.info("Sales handlers initialized successfully")


def get_sales_tool_names() -> list[str]:
    """
    Return list of registered sales tool names (dynamically discovered).

    This function provides dynamic tool discovery without hardcoding tool lists.
    Tools are registered via sales_tool_registry.register_tool() as they're
    defined, and this function returns the discovered list.

    BENEFITS:
    - No hardcoded lists to maintain
    - Single source of truth: the tool decorator + registry call
    - Automatically includes newly registered tools
    - No risk of forgetting to update this list

    Returns:
        List of sales tool names registered in this module
    """
    return sales_tool_registry.get_tools_by_category("sales")


def get_pageable_tool_names() -> list[str]:
    """
    Return list of product tools that return pageable result lists (dynamically discovered).

    Pageable tools are those that return collections of items (not single items)
    and support client-side pagination. This enables dynamic tool discovery for
    pagination features without hardcoding tool lists in client code.

    These tools return results in pageable formats:
    - {"items": [...], "count": N} - structured format
    - Direct list - fallback format

    BENEFITS:
    - No hardcoded lists to maintain
    - Single source of truth: the pageable_tool_registry
    - Automatically updated when tools are marked as pageable

    Returns:
        List of product tool names that support pagination
    """
    return pageable_tool_registry.get_tools_by_category("pageable")


def register_tools() -> None:
    """Register all MCP tools."""

    @mcp.tool(  # type: ignore[union-attr]
        annotations=ToolAnnotations(
            title="Fetch Product by SKU",
            readOnlyHint=True,
            idempotentHint=True,
        )
    )
    async def fetch_by_sku(ctx: Context, sku: str) -> dict[str, Any] | None:
        """
        Fetch product details by exact SKU code (Stock Keeping Unit).

        ** WHEN TO USE THIS TOOL **:
        ✅ Client explicitly mentions a product code/SKU
        ✅ Query contains patterns like: "SKU XXX", "code YYY", "product ZZZ-####"
        ✅ Client asks for "the product [CODE]" or "product [CODE]"

        ** EXAMPLES OF VALID USE **:
        - "I want the TOY-0018"
        - "looking for product COMP-0038"
        - "give me info about SKU HOME-0007"
        - "product AUTO-0016"

        ** DON'T USE WHEN **:
        ❌ Client mentions product name without code ("looking for laptop")
        ❌ Query is conceptual/need-based ("something to clean")
        ❌ Query has typos in SKU (use fuzzy_search_smart instead)

        ** PERFORMANCE **: Ultra-fast (~9ms average) - Direct database lookup

        Args:
            ctx: MCP context for logging and progress
            sku: The exact product SKU to search for (case-sensitive)
                 Format examples: COMP-0009, TOY-0018, HOME-0007

        Returns:
            Product details dict if found, None otherwise
            Returns: {id, sku, name, description, category, brand, tags, color, size, price, image_url}
        """
        try:
            await ctx.debug(f"fetch_by_sku called with sku={sku}")
            result = await fetch_by_sku_async(sku)  # Async DB call

            if result:
                await ctx.info(f"Product found: {result.get('name', 'Unknown')}")
            else:
                await ctx.warning(f"No product found for SKU: {sku}")

            return result
        except Exception as e:
            await ctx.error(f"Error in fetch_by_sku: {e!s}")
            raise

    @mcp.tool(  # type: ignore[union-attr]
        annotations=ToolAnnotations(
            title="Fetch Product by ID",
            readOnlyHint=True,
            idempotentHint=True,
        )
    )
    async def fetch_by_id(ctx: Context, product_id: int) -> dict[str, Any] | None:
        """
        Fetch product details by ID.

        Args:
            ctx: MCP context for logging and progress
            product_id: The product ID to search for

        Returns:
            Product details if found, None otherwise
        """
        try:
            await ctx.debug(f"fetch_by_id called with product_id={product_id}")
            result = await fetch_by_id_async(product_id)  # Async DB call

            if result:
                await ctx.info(f"Product found: {result.get('name', 'Unknown')}")
            else:
                await ctx.warning(f"No product found for ID: {product_id}")

            return result
        except Exception as e:
            await ctx.error(f"Error in fetch_by_id: {e!s}")
            raise

    @mcp.tool(  # type: ignore[union-attr]
        annotations=ToolAnnotations(
            title="Semantic Product Search",
            readOnlyHint=True,
            openWorldHint=True,  # Results may vary with embedding model
        )
    )
    async def search_products(
        ctx: Context, query: str, limit: int = 20, offset: int = 0
    ) -> dict[str, Any]:
        """
        Search products using semantic/conceptual search with AI embeddings (Gemini).

        ** WHEN TO USE THIS TOOL **:
        ✅ Client describes a NEED or BENEFIT (not a specific product name)
        ✅ Conceptual/abstract queries about PURPOSE or USE CASE
        ✅ Queries with patterns: "something for...", "I need to...", "I want to..."
        ✅ Client describes what they want to ACHIEVE, not what they want to BUY

        ** EXAMPLES OF VALID USE **:
        - "something to automatically clean my house"
        - "I need to improve my computer, I want more speed"
        - "protect my phone from drops"
        - "work from home professionally"
        - "exercise at home"
        - "something to sleep better"
        - "light my room intelligently"

        ** DON'T USE WHEN **:
        ❌ Client mentions specific product name ("looking for laptop", "want keyboard")
        ❌ Client asks about a category ("gaming products", "what's in home")
        ❌ Query has typos in product names (use fuzzy_search_smart)
        ❌ Client mentions exact SKU/code (use fetch_by_sku)

        ** HOW IT WORKS **:
        - Uses Google Gemini embedding-001 to convert query → 1536-dim vector
        - Compares semantic meaning (not exact words) with product embeddings
        - Finds products by WHAT THEY DO, not just what they're called
        - Example: "clean automatically" → finds robot vacuums (even without word "robot")

        ** PERFORMANCE **:
        - Average: ~490ms (slower than fuzzy_search_smart due to AI embedding generation)
        - Use when semantic understanding is critical, not for simple name lookups

        ** SUCCESS RATE **: 100% on conceptual queries (improved from 87% after fallback system)

        Args:
            ctx: MCP context for logging and progress
            query: Conceptual search query describing need/benefit/use case
            limit: Number of results to return (default: 20, max: 100)
            offset: Number of results to skip for pagination (default: 0)

        Returns:
            PaginatedResponse with items, count, total_count, and pagination metadata
            Each product: {id, sku, name, description, category, brand, tags, color, size, price, image_url}
        """
        try:
            # Concurrency control - limits max concurrent requests
            try:
                async with acquire_slot():
                    # Rate limiting check
                    session_key = ctx.request_id or "anonymous"
                    if not search_limiter.check(session_key):
                        await ctx.warning("Search rate limit exceeded")
                        return {
                            "items": [],
                            "count": 0,
                            "total_count": 0,
                            "query": query,
                            "rate_limited": True,
                        }

                    # Progress reporting for semantic search (can be slow ~490ms)
                    await ctx.report_progress(progress=0.1, total=1.0)
                    await ctx.info(f"Starting semantic search for: {query}")

                    await ctx.report_progress(progress=0.3, total=1.0)
                    await ctx.debug("Generating embedding with Gemini API")

                    # Call async function with pagination - returns PaginatedResponse dict
                    result = await search_products_async(query, limit=limit, offset=offset)

                    await ctx.report_progress(progress=1.0, total=1.0)
                    await ctx.info(f"Semantic search completed: {result.get('count', 0)} results")

                    return result
            except ConcurrencyLimitExceeded:
                await ctx.warning("Server at capacity, too many concurrent requests")
                return {
                    "items": [],
                    "count": 0,
                    "total_count": 0,
                    "query": query,
                    "concurrency_limited": True,
                }
        except Exception as e:
            await ctx.error(f"Error in search_products: {e!s}")
            raise

    @mcp.tool(  # type: ignore[union-attr]
        annotations=ToolAnnotations(
            title="Fuzzy Text Search",
            readOnlyHint=True,
            idempotentHint=True,
        )
    )
    async def fuzzy_search_smart(
        ctx: Context,
        query: str,
        fields: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
        strict_threshold: float = 0.25,
        word_threshold: float = 0.35,
        fallback_threshold: float = 0.15,
        name_weight: float = 2.0,
        description_weight: float = 1.0,
        category_weight: float = 1.5,
        brand_weight: float = 1.0,
    ) -> dict[str, Any]:
        """
        Smart fuzzy text search with typo tolerance and category support (PostgreSQL pg_trgm).

        ** WHEN TO USE THIS TOOL **:
        ✅ Client mentions SPECIFIC PRODUCT NAME (even with typos)
        ✅ Client asks about PRODUCT CATEGORY ("what's in home", "gaming products")
        ✅ Query contains TYPOS or SPELLING ERRORS in product names
        ✅ Client wants to browse a category without specific needs

        ** EXAMPLES OF VALID USE **:
        Product name searches:
        - "looking for mechanical keyboard"
        - "I need wireless headphones"
        - "I want an office chair"
        - "studio headphons" (with typo 'headphons')
        - "robbot vacuum" (with typo 'robbot')
        - "waterprof jacket" (with typo 'waterprof')

        Category searches (NEW - improved from 40% → 100% success rate):
        - "what's in home"
        - "computing products"
        - "do you have sports stuff"
        - "what do you sell in audio"
        - "show me kitchen products"
        - "office products"

        ** DON'T USE WHEN **:
        ❌ Query is conceptual/need-based ("something to clean", "work from home")
        ❌ Client mentions exact SKU code (use fetch_by_sku)
        ❌ Query describes benefits/purposes rather than product names (use search_products)

        ** HOW IT WORKS - 4-TIER FALLBACK STRATEGY **:
        1. Tier 1 (strict_threshold=0.25): Standard trigram similarity search
        2. Tier 2 (word_threshold=0.35): Word similarity for better partial/typo matching (weighted)
        2.5. Tier 2.5 (word_threshold=0.35): Token-based search (splits query into individual words)
        3. Tier 3 (fallback_threshold=0.15): Relaxed threshold as final attempt

        Returns results from first successful tier. Each result includes 'search_tier' field
        showing which tier succeeded: 'standard', 'word_similarity', 'token_based', or 'fallback'.

        ** TIER 2.5 EXPLANATION (NEW 2025-10-03) **:
        When multi-word queries fail in Tier 2 due to irrelevant terms diluting similarity:
        - Example: "electric pans" → whole phrase similarity = 0.200 (fails threshold 0.4)
        - Tier 2.5 splits into tokens: ["electric", "pans"]
        - Evaluates each token separately: "pans" → 0.444 ✅ (passes threshold)
        - Returns products matching ANY token with highest individual token score
        - This solves the problem where users add modifiers that don't exist in product names

        ** POSITION-BASED TOKEN WEIGHTING (NEW 2025-10-03) **:
        Tier 2.5 applies position-based weights to prioritize earlier tokens (usually nouns):
        - First token: weight 1.0 (highest priority - typically the main product name)
        - Second token: weight 0.5 (medium priority - typically a modifier)
        - Third+ tokens: weight 0.33, 0.25... (decreasing priority)
        - Formula: position_weight = 1.0 / (position + 1)
        - Example: "electric pans" → "pans" (pos 0, weight 1.0) prioritized over
          "electric" (pos 1, weight 0.5), even if "electric" has higher raw similarity
        - This prevents irrelevant modifiers from outranking the main search term

        ** KEY IMPROVEMENT (2025-10-03) **:
        Now searches in name, description, AND category fields by default (was name/description only).
        This enabled 60-point improvement in category searches: 40% → 100% success rate.
        Category field is indexed with GIN pg_trgm for ultra-fast performance.

        ** WEIGHTED SCORING (NEW 2025-10-03) **:
        Tier 2 now uses weighted scoring to prioritize name matches over description matches.
        This fixes issues like "electric pan" returning "Adjustable Desk" (has "electric"
        in description) before "Non-Stick Pan" (has "pan" in name).

        Default weights:
        - name: 2.0 (highest priority - product name is most important)
        - category: 1.5 (high priority - helps with category searches)
        - description: 1.0 (medium priority - supplementary info)
        - brand: 1.0 (medium priority - brand matching)

        ** PERFORMANCE **:
        - Average: ~10.8ms (45x faster than semantic search)
        - Uses PostgreSQL trigram similarity with normalized text (accent-insensitive)
        - Category queries: <12ms even with category field scan
        - Weighted scoring adds <1ms overhead

        ** ACCENT & CASE INSENSITIVE **:
        - "camera" matches "cámara" (accent-insensitive)
        - "LAPTOP" matches "laptop" (case-insensitive)
        - Uses normalize_text() function: unaccent + lowercase

        Args:
            ctx: MCP context for logging and progress
            query: Product name, category, or search term (typos OK)
            fields: Fields to search (default: ['name', 'description', 'category'])
                   Available: 'name', 'description', 'brand', 'category'
            limit: Maximum results to return (default: 20, max: 100)
            offset: Number of results to skip for pagination (default: 0)
            strict_threshold: Tier 1 similarity threshold (default: 0.25 = 25% match)
            word_threshold: Tier 2 word similarity threshold (default: 0.35 = 35% match)
            fallback_threshold: Tier 3 relaxed threshold (default: 0.15 = 15% match)
            name_weight: Weight for name field (default: 2.0 - prioritize name matches)
            description_weight: Weight for description field (default: 1.0)
            category_weight: Weight for category field (default: 1.5)
            brand_weight: Weight for brand field (default: 1.0)

        Returns:
            PaginatedResponse with items, count, total_count, and pagination metadata
            Each product includes: id, sku, name, description, category, brand, tags, color, size, price, image_url, max_similarity, search_tier, [field]_similarity
        """
        try:
            # Concurrency control - limits max concurrent requests
            try:
                async with acquire_slot():
                    # Rate limiting check
                    session_key = ctx.request_id or "anonymous"
                    if not search_limiter.check(session_key):
                        await ctx.warning("Search rate limit exceeded")
                        return {"items": [], "count": 0, "query": query, "rate_limited": True}

                    await ctx.info(f"Fuzzy search started for: {query}")
                    await ctx.report_progress(progress=0.1, total=1.0)

                    # Default to searching in name, description, and category
                    if fields is None:
                        fields = ["name", "description", "category"]

                    await ctx.debug(f"Searching in fields: {fields}")
                    await ctx.report_progress(progress=0.3, total=1.0)

                    # Call async fuzzy search directly
                    result = await fuzzy_search_smart_async(
                        query=query,
                        fields=fields,
                        limit=limit,
                        offset=offset,
                        strict_threshold=strict_threshold,
                        word_threshold=word_threshold,
                        fallback_threshold=fallback_threshold,
                        name_weight=name_weight,
                        description_weight=description_weight,
                        category_weight=category_weight,
                        brand_weight=brand_weight,
                    )

                    await ctx.report_progress(progress=0.6, total=1.0)

                    # Extract items from the PaginatedResponse dict
                    items = result.get("items", [])

                    # FALLBACK: If fuzzy search found nothing or has low confidence, try semantic
                    low_confidence_results = items and items[0].get("max_similarity", 1.0) < 0.5

                    if not items or low_confidence_results:
                        await ctx.info("Trying semantic fallback search")
                        await ctx.report_progress(progress=0.8, total=1.0)
                        try:
                            semantic_result = await search_products_async(
                                query, limit=limit, offset=offset
                            )
                            semantic_items = semantic_result.get("items", [])
                            if semantic_items:
                                for r in semantic_items:
                                    r["search_tier"] = "semantic_fallback"
                                result = semantic_result
                                result["items"] = semantic_items
                                items = semantic_items
                                await ctx.info(f"Semantic fallback succeeded: {len(items)} results")
                        except Exception as e:
                            await ctx.warning(f"Semantic fallback failed: {e!s}")

                    await ctx.report_progress(progress=1.0, total=1.0)

                    # Log search tier information
                    if items and len(items) > 0:
                        tier = items[0].get("search_tier", "unknown")
                        max_sim = items[0].get("max_similarity", "N/A")
                        await ctx.info(
                            f"Search completed: {len(items)} products, tier={tier}, max_similarity={max_sim}"
                        )
                    else:
                        await ctx.info("Search completed: no matches found")

                    return result
            except ConcurrencyLimitExceeded:
                await ctx.warning("Server at capacity, too many concurrent requests")
                return {"items": [], "count": 0, "query": query, "concurrency_limited": True}
        except Exception as e:
            await ctx.error(f"Error in fuzzy_search_smart: {e!s}")
            raise

    @mcp.tool(  # type: ignore[union-attr]
        annotations=ToolAnnotations(
            title="Visual Similarity Search",
            readOnlyHint=True,
            idempotentHint=True,
        )
    )
    async def search_products_by_embedding(
        ctx: Context,
        image_embedding: list[float],
        limit: int = 5,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        Search products using image embedding vector for visual similarity (Google Lens style).

        ** WHEN TO USE THIS TOOL **:
        ✅ User has sent a PHOTO of a product and you have an image_embedding
        ✅ Visual search context - finding products that LOOK similar
        ✅ When image_embedding is provided in the conversation context

        ** EXAMPLES OF VALID USE **:
        - User sends photo of a laptop → find similar laptops by appearance
        - User sends photo of a shoe → find visually similar shoes
        - User sends photo of any product → find matching products

        ** DON'T USE WHEN **:
        ❌ No image_embedding is provided (use fuzzy_search_smart instead)
        ❌ User is searching by text/name (use fuzzy_search_smart)
        ❌ User is searching by concept/need (use search_products)

        ** HOW IT WORKS **:
        - Compares the provided 1536-dim embedding with product embeddings
        - Uses cosine similarity for accurate visual matching
        - Returns products ordered by visual similarity score (0-1)

        ** PERFORMANCE **:
        - Ultra-fast: ~10-15ms (no embedding generation needed)
        - Direct vector comparison using pgvector

        Args:
            ctx: MCP context for logging and progress
            image_embedding: 1536-dimensional embedding vector from image
            limit: Number of results to return (default: 5, max: 100)
            offset: Number of results to skip for pagination (default: 0)

        Returns:
            PaginatedResponse with items, count, total_count, and pagination metadata
            Each product includes: id, sku, name, description, category, brand, tags,
            color, size, price, image_url, similarity_score (0-1, higher = more similar)
        """
        try:
            # Concurrency control
            try:
                async with acquire_slot():
                    # Rate limiting check
                    session_key = ctx.request_id or "anonymous"
                    if not search_limiter.check(session_key):
                        await ctx.warning("Search rate limit exceeded")
                        return {
                            "items": [],
                            "count": 0,
                            "total_count": 0,
                            "rate_limited": True,
                        }

                    # Validate embedding dimension
                    if len(image_embedding) != 1536:
                        await ctx.error(
                            f"Invalid embedding dimension: {len(image_embedding)}, expected 1536"
                        )
                        return {
                            "items": [],
                            "count": 0,
                            "total_count": 0,
                            "error": f"Invalid embedding dimension: {len(image_embedding)}",
                        }

                    await ctx.report_progress(progress=0.1, total=1.0)
                    await ctx.info(
                        f"Starting visual similarity search with {len(image_embedding)}-dim embedding"
                    )

                    # Call async function with pagination
                    result = await search_products_by_embedding_async(
                        image_embedding=image_embedding,
                        limit=limit,
                        offset=offset,
                    )

                    await ctx.report_progress(progress=1.0, total=1.0)
                    items = result.get("items", [])

                    if items:
                        top_similarity = items[0].get("similarity_score", 0)
                        await ctx.info(
                            f"Visual search completed: {len(items)} results, "
                            f"top similarity: {top_similarity:.3f}"
                        )
                    else:
                        await ctx.info("Visual search completed: no matches found")

                    return result

            except ConcurrencyLimitExceeded:
                await ctx.warning("Server at capacity, too many concurrent requests")
                return {
                    "items": [],
                    "count": 0,
                    "total_count": 0,
                    "concurrency_limited": True,
                }
        except Exception as e:
            await ctx.error(f"Error in search_products_by_embedding: {e!s}")
            raise

    @mcp.tool(  # type: ignore[union-attr]
        annotations=ToolAnnotations(
            title="BANT Lead Qualification",
            readOnlyHint=False,  # Creates database record
            idempotentHint=False,  # Each call creates new lead record
        )
    )
    async def analyze_lead_bant(
        ctx: Context,
        conversation_id: str,
        user_id: str | None = None,
        channel: str = "telegram",
    ) -> dict[str, Any]:
        """
        Analyze conversation for BANT lead qualification (Budget, Authority, Need, Timeline).

        ** WHEN TO USE THIS TOOL **:
        ✅ Customer shows BUYING INTENT (asks about prices, availability, how to order)
        ✅ Customer mentions BUDGET, TIMELINE, or DECISION-MAKING AUTHORITY
        ✅ Conversation has 3+ messages about specific products
        ✅ Before ENDING a sales conversation (to record qualification)
        ✅ Customer uses phrases like:
           - "quiero comprar", "cómo ordeno", "cuánto cuesta", "está disponible"
           - "tengo presupuesto de...", "mi límite es...", "puedo pagar..."
           - "soy el gerente", "decido las compras", "mi jefe aprobó..."
           - "lo necesito para...", "antes de fin de mes", "es urgente"

        ** DON'T USE WHEN **:
        ❌ Customer is just browsing or asking general questions
        ❌ No buying signals detected in conversation
        ❌ Conversation has less than 3 substantive messages

        ** HOW IT WORKS **:
        1. Retrieves conversation history from database (nlp_conversation_history)
        2. Aggregates user messages into analysis text
        3. Calls BANT service with Gemini AI for scoring
        4. Returns qualification tier and actionable recommendation

        ** QUALIFICATION TIERS **:
        - Hot (8-10): Customer ready to buy. Prioritize closure, offer payment options.
        - Warm (6-7): Good prospect. Continue nurturing, answer questions, suggest products.
        - Cold (4-5): Early stage. Provide general info without pressure.
        - Unqualified (0-3): Not a qualified prospect. Respond politely, don't push sale.

        ** HOW TO USE THE RESULT **:
        - Hot: "¡Excelente elección! ¿Te gustaría que te ayude con el proceso de compra?"
        - Warm: "Tenemos varias opciones que podrían interesarte. ¿Quieres que te muestre más?"
        - Cold: "Aquí tienes la información. Estoy disponible si tienes más preguntas."
        - Unqualified: "¿Hay algo más en lo que pueda ayudarte hoy?"

        ** PERFORMANCE **:
        - Average: ~2-3 seconds (includes AI analysis)
        - Creates a database record for analytics

        Args:
            ctx: MCP context for logging and progress
            conversation_id: Telegram chat_id or session identifier (required)
            user_id: Optional user UUID for customer-level analytics
            channel: Source channel - telegram, whatsapp, web, api (default: telegram)

        Returns:
            Dict with qualification results:
            - analyzed: bool - True if analysis succeeded
            - lead_id: UUID of created lead record
            - overall_score: Weighted BANT score (0-10)
            - budget_score, authority_score, need_score, timeline_score: Individual scores
            - qualification: Tier name (hot, warm, cold, unqualified)
            - qualification_label: Human-readable tier label
            - recommendation: Actionable guidance in Spanish
            - message_count: Number of messages analyzed
            - error: Error message if analysis failed
        """
        try:
            await ctx.report_progress(progress=0.1, total=1.0)
            await ctx.info(f"Starting BANT analysis for conversation: {conversation_id}")

            # Call the async analyzer
            result = await analyze_lead_bant_async(
                conversation_id=conversation_id,
                user_id=user_id,
                channel=channel,
            )

            await ctx.report_progress(progress=1.0, total=1.0)

            if result.get("analyzed"):
                await ctx.info(
                    f"BANT analysis completed: score={result.get('overall_score')}, "
                    f"tier={result.get('qualification')}"
                )
            else:
                await ctx.warning(f"BANT analysis failed: {result.get('error')}")

            return result

        except Exception as e:
            await ctx.error(f"Error in analyze_lead_bant: {e!s}")
            raise

    # === DYNAMIC TOOL REGISTRATION ===
    # Register each tool in the appropriate category (no hardcoding!)
    # This replaces the hardcoded lists in get_sales_tool_names() and get_pageable_tool_names()
    sales_tools = [
        "fetch_by_sku",
        "fetch_by_id",
        "search_products",
        "fuzzy_search_smart",
        "search_products_by_embedding",
        "analyze_lead_bant",
    ]
    sales_tool_registry.register_tools(sales_tools, "sales")

    # Also mark which tools support pagination
    pageable_tools = [
        "fuzzy_search_smart",
        "search_products",
        "search_products_by_embedding",
    ]
    pageable_tool_registry.register_tools(pageable_tools, "pageable")

    logger.info(f"Registered {len(sales_tools)} sales tools + {len(pageable_tools)} pageable tools")
