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

# Confidence tier thresholds for visual search results (Context7 best practice)
# Follows the same 4-tier system as fuzzy_search.py for consistency
HIGH_CONFIDENCE_THRESHOLD = 0.75  # ≥75%: Show products confidently
MEDIUM_CONFIDENCE_THRESHOLD = 0.60  # 60-75%: Show with "might interest you" note
LOW_CONFIDENCE_THRESHOLD = 0.45  # 45-60%: Show with low_confidence flag
# Below 45%: Filter out (not similar enough to be useful)


async def search_products_by_embedding_async(
    image_embedding: list[float],
    limit: int = PaginationDefaults.SEARCH_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """Search products by visual similarity using image embedding vectors.

    Performs visual similarity search by comparing the provided image embedding
    with stored product image_embeddings using cosine distance (pgvector).

    This is used for "Google Lens style" visual search:
    - User sends a photo of a product
    - OCR service generates 1536-dim embedding from image description
    - This function finds visually similar products

    Implementation:
    - Uses PostgreSQL pgvector extension with <=> (cosine distance) operator
    - Searches indexed image_embedding column (vector(1536) type, from Vision AI)
    - Separate from text embedding column (used for text-based search)
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

    # First get total count of products with image embeddings
    count_sql = (
        f"SELECT COUNT(*) as total FROM {settings.SCHEMA_NAME}.products "
        f"WHERE image_embedding IS NOT NULL"
    )

    # Use cosine distance (<=> operator) for better similarity comparison
    # Cosine distance is 1 - cosine_similarity, so lower is more similar
    # We calculate similarity as 1 - cosine_distance for intuitive 0-1 scale
    # Note: Uses image_embedding (from Vision AI) for visual search
    sql = f"""
        SELECT
            id, sku, name, description, category, brand, tags, color, size, price, image_url,
            1 - (image_embedding <=> $1) AS similarity_score
        FROM {settings.SCHEMA_NAME}.products
        WHERE image_embedding IS NOT NULL
        ORDER BY image_embedding <=> $1
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
        best_match_score = rows[0].get("similarity_score", 0) if rows else 0
        if rows:
            logger.debug(
                "Top match: %s (similarity: %.3f)",
                rows[0].get("name", "Unknown"),
                best_match_score,
            )

        # Classify results by confidence tier (4-tier system like fuzzy_search.py)
        high_confidence = [
            r for r in rows if r.get("similarity_score", 0) >= HIGH_CONFIDENCE_THRESHOLD
        ]
        medium_confidence = [
            r
            for r in rows
            if MEDIUM_CONFIDENCE_THRESHOLD
            <= r.get("similarity_score", 0)
            < HIGH_CONFIDENCE_THRESHOLD
        ]
        low_confidence = [
            r
            for r in rows
            if LOW_CONFIDENCE_THRESHOLD
            <= r.get("similarity_score", 0)
            < MEDIUM_CONFIDENCE_THRESHOLD
        ]

        # Determine which tier to use (prioritize higher confidence)
        if high_confidence:
            items = high_confidence[: params.limit]
            confidence_tier = "high"
        elif medium_confidence:
            items = medium_confidence[: params.limit]
            confidence_tier = "medium"
        elif low_confidence:
            # Mark items as low_confidence (same pattern as fuzzy_search Tier 3)
            for item in low_confidence:
                item["low_confidence"] = True
            items = low_confidence[: params.limit]
            confidence_tier = "low"
        else:
            items = []
            confidence_tier = "none"

        logger.info(
            "visual_search_tier_classification: tier=%s, high=%d, medium=%d, low=%d, "
            "best_score=%.3f, returning=%d items",
            confidence_tier,
            len(high_confidence),
            len(medium_confidence),
            len(low_confidence),
            best_match_score,
            len(items),
        )

        # Build paginated response with confidence metadata
        # Note: extra fields are passed as **kwargs, not as a dict
        response = PaginatedResponse.create(
            items=items,
            total_count=total_count,
            params=params,
            search_type="embedding_similarity",
            confidence_tier=confidence_tier,
            best_match_score=best_match_score,
        )

        return response.to_dict()

    except Exception as e:
        logger.error("Error in embedding similarity search: %s", e)
        raise
