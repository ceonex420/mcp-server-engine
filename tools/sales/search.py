"""Semantic product search using vector embeddings.

Provides AI-powered conceptual search by converting queries into vectors.
All operations are async for non-blocking database access.

Author: Odiseo Team
Version: 2.0.0
"""

from typing import Any

from config import settings
from utils.db_async import fetchall_async
from utils.embeddings import emb_client
from utils.logger import get_logger
from utils.pagination import PaginatedResponse, PaginationDefaults, PaginationParams
from utils.validation import validate_schema_name

# Get logger for search operations
logger = get_logger("mcp_tools_search")


async def search_products_async(
    query: str,
    limit: int = PaginationDefaults.SEARCH_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """Semantic product search using vector embeddings (Google Gemini embedding-001).

    Performs AI-powered conceptual search by converting the query into a 1536-dimensional
    vector and finding products with similar semantic meaning (not just keyword matching).

    Implementation:
    - Generates query embedding using Google Gemini embedding-001
    - Uses PostgreSQL pgvector extension with <-> (L2 distance) operator
    - Searches indexed embedding column (vector(1536) type)
    - Returns products ordered by semantic similarity

    Use cases:
    - Conceptual queries: "something to automatically clean"
    - Need-based searches: "work from home professionally"
    - Benefit/purpose queries: "protect my phone from drops"

    Performance: ~490ms average (embedding generation + vector search)

    Args:
        query: Conceptual search query describing need, benefit, or use case
        limit: Number of top results to return (default: 20, max: 100)
        offset: Number of results to skip for pagination (default: 0)

    Returns:
        PaginatedResponse dict with items, count, total_count, and pagination metadata
        Each item: {id, sku, name, description, category, brand, tags, color, size, price}

    Raises:
        Exception: If embedding generation fails or database error occurs
    """
    # Validate pagination parameters
    params = PaginationParams.for_search(limit=limit, offset=offset)
    logger.info(
        "Starting vector search for query: '%s' (limit=%d, offset=%d)",
        query,
        params.limit,
        params.offset,
    )

    vectors = emb_client.embed([query])

    if not vectors:
        logger.warning("Could not generate embeddings for query")
        return PaginatedResponse.empty(params, query=query).to_dict()

    qvec = vectors[0]
    logger.debug("Vector generated for query (dimension: %d)", len(qvec))

    # Validate schema name to prevent SQL injection
    validate_schema_name(settings.SCHEMA_NAME)

    # First get total count of products with embeddings
    count_sql = (
        f"SELECT COUNT(*) as total FROM {settings.SCHEMA_NAME}.products WHERE embedding IS NOT NULL"
    )

    # asyncpg uses $1, $2, etc. for parameters
    sql = (
        f"SELECT id, sku, name, description, category, brand, tags, color, size, price,"
        f" embedding <-> $1 AS distance"
        f" FROM {settings.SCHEMA_NAME}.products"
        f" WHERE embedding IS NOT NULL"
        f" ORDER BY embedding <-> $1"
        f" LIMIT $2 OFFSET $3"
    )

    try:
        # Get total count
        count_result = await fetchall_async(count_sql)
        total_count = count_result[0]["total"] if count_result else 0

        # Pass vector directly - pgvector/asyncpg handles the conversion
        rows = await fetchall_async(sql, qvec, params.limit, params.offset)
        logger.info("Vector search completed: %d results found", len(rows))

        # Don't expose distance in results
        for r in rows:
            r.pop("distance", None)

        # Build paginated response
        response = PaginatedResponse.create(
            items=rows,
            total_count=total_count,
            params=params,
            query=query,
        )

        return response.to_dict()

    except Exception as e:
        logger.error("Error in vector search: %s", e)
        raise
