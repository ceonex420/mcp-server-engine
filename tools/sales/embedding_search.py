"""Visual similarity search using image embeddings.

Provides product search by comparing image embeddings with product embeddings.
All operations are async for non-blocking database access.

Author: Odiseo Team
Version: 1.0.0
"""

from typing import Any

from config import settings
from utils.db_async import fetchall_async
from utils.logger import get_logger
from utils.pagination import PaginatedResponse, PaginationDefaults, PaginationParams
from utils.validation import validate_schema_name

logger = get_logger("mcp_tools_embedding_search")


async def search_products_by_embedding_async(
    image_embedding: list[float],
    limit: int = PaginationDefaults.SEARCH_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """Search products by visual similarity using image embedding vectors.

    Performs visual similarity search by comparing the provided image embedding
    with stored product embeddings using cosine distance (pgvector).

    This is used for "Google Lens style" visual search:
    - User sends a photo of a product
    - OCR service generates 1536-dim embedding
    - This function finds visually similar products

    Implementation:
    - Uses PostgreSQL pgvector extension with <=> (cosine distance) operator
    - Searches indexed embedding column (vector(1536) type)
    - Returns products ordered by visual similarity

    Use cases:
    - User sends photo of laptop → returns similar laptops
    - User sends photo of product → finds matching products

    Performance: ~10-15ms average (direct vector comparison, no embedding generation)

    Args:
        image_embedding: 1536-dimensional embedding vector from image
        limit: Number of top results to return (default: 20, max: 100)
        offset: Number of results to skip for pagination (default: 0)

    Returns:
        PaginatedResponse dict with items, count, total_count, and pagination metadata
        Each item includes: id, sku, name, description, category, brand, tags,
        color, size, price, image_url, similarity_score

    Raises:
        ValueError: If embedding dimension is incorrect
        Exception: If database error occurs
    """
    # Validate embedding dimension
    expected_dim = settings.EMBEDDING_DIMENSION
    if len(image_embedding) != expected_dim:
        raise ValueError(
            f"Image embedding must have {expected_dim} dimensions, got {len(image_embedding)}"
        )

    # Validate pagination parameters
    params = PaginationParams.for_search(limit=limit, offset=offset)
    logger.info(
        "Starting embedding similarity search (limit=%d, offset=%d)",
        params.limit,
        params.offset,
    )

    # Validate schema name to prevent SQL injection
    validate_schema_name(settings.SCHEMA_NAME)

    # First get total count of products with embeddings
    count_sql = (
        f"SELECT COUNT(*) as total FROM {settings.SCHEMA_NAME}.products "
        f"WHERE embedding IS NOT NULL"
    )

    # Use cosine distance (<=> operator) for better similarity comparison
    # Cosine distance is 1 - cosine_similarity, so lower is more similar
    # We calculate similarity as 1 - cosine_distance for intuitive 0-1 scale
    sql = f"""
        SELECT
            id, sku, name, description, category, brand, tags, color, size, price, image_url,
            1 - (embedding <=> $1) AS similarity_score
        FROM {settings.SCHEMA_NAME}.products
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> $1
        LIMIT $2 OFFSET $3
    """

    try:
        # Get total count
        count_result = await fetchall_async(count_sql)
        total_count = count_result[0]["total"] if count_result else 0

        # Pass vector directly - pgvector/asyncpg handles the conversion
        rows = await fetchall_async(sql, image_embedding, params.limit, params.offset)
        logger.info(
            "Embedding similarity search completed: %d results found",
            len(rows),
        )

        # Log top match similarity for debugging
        if rows:
            top_similarity = rows[0].get("similarity_score", 0)
            logger.debug(
                "Top match: %s (similarity: %.3f)",
                rows[0].get("name", "Unknown"),
                top_similarity,
            )

        # Build paginated response
        response = PaginatedResponse.create(
            items=rows,
            total_count=total_count,
            params=params,
            extra={"search_type": "embedding_similarity"},
        )

        return response.to_dict()

    except Exception as e:
        logger.error("Error in embedding similarity search: %s", e)
        raise
