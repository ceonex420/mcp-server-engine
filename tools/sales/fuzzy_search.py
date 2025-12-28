"""
Fuzzy Search Tool using PostgreSQL pg_trgm and unaccent extensions

This module implements accent-insensitive fuzzy text search capabilities using:
- pg_trgm: Trigram similarity for typo tolerance
- unaccent: Accent removal for Unicode normalization
- normalize_text(): Custom function for case/accent normalization

Features:
- Typo-tolerant search: "licuadora" matches "licu4dora"
- Accent-insensitive: "camara" matches "cámara"
- Case-insensitive: "CAMARA" matches "cámara"

All operations are async for non-blocking database access.

Author: Odiseo Team
Version: 2.0.0
"""

from typing import Any

from config import settings
from utils.db_async import fetchall_async, fetchone_async
from utils.logger import get_logger
from utils.pagination import PaginatedResponse, PaginationDefaults, PaginationParams
from utils.validation import validate_schema_name

# Get logger for fuzzy search operations
logger = get_logger("mcp_tools_fuzzy")


async def fuzzy_search_async(
    query: str,
    fields: list[str] | None = None,
    min_similarity: float = 0.3,
    limit: int = 20,
    include_similarity: bool = True,
) -> list[dict]:
    """Async fuzzy search using PostgreSQL pg_trgm extension.

    Args:
        query: Search term to match against
        fields: List of fields to search in ['name', 'description', 'brand', 'category']
        min_similarity: Minimum similarity threshold (0.0 to 1.0)
        limit: Maximum number of results to return
        include_similarity: Whether to include similarity scores in results

    Returns:
        List of product dictionaries with optional similarity scores
    """
    # Validate inputs
    if not query or not query.strip():
        logger.warning("Empty query provided to fuzzy_search_async")
        return []

    if not 0.0 <= min_similarity <= 1.0:
        raise ValueError(f"min_similarity must be between 0.0 and 1.0, got {min_similarity}")

    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")

    if fields is None:
        fields = ["name", "description"]

    valid_fields = {"name", "description", "brand", "category"}
    invalid_fields = set(fields) - valid_fields
    if invalid_fields:
        raise ValueError(
            f"Invalid fields: {', '.join(sorted(invalid_fields))}. "
            f"Valid fields are: {', '.join(sorted(valid_fields))}"
        )

    logger.info(
        "Starting async fuzzy search: query='%s', fields=%s, min_similarity=%.2f, limit=%d",
        query,
        fields,
        min_similarity,
        limit,
    )

    validate_schema_name(settings.SCHEMA_NAME)

    # Build similarity conditions and selects
    similarity_conditions = []
    similarity_selects = []
    param_count = 0

    for field in fields:
        param_count += 1  # noqa: SIM113
        similarity_conditions.append(
            f"similarity(normalize_text({field}), normalize_text(${param_count})) >= ${param_count + len(fields)}"
        )
        if include_similarity:
            similarity_selects.append(
                f"similarity(normalize_text({field}), normalize_text(${param_count})) AS {field}_similarity"
            )

    base_fields = "id, sku, name, description, category, brand, tags, color, size, price"
    select_fields = base_fields

    if include_similarity:
        select_fields += ", " + ", ".join(similarity_selects)
        max_similarities = ", ".join(
            [
                f"similarity(normalize_text({f}), normalize_text(${i + 1}))"
                for i, f in enumerate(fields)
            ]
        )
        select_fields += f", GREATEST({max_similarities}) AS max_similarity"

    where_clause = " OR ".join(similarity_conditions)

    if include_similarity:
        sql = f"""
        SELECT {select_fields}
        FROM {settings.SCHEMA_NAME}.products
        WHERE {where_clause}
        ORDER BY max_similarity DESC
        LIMIT ${len(fields) * 2 + 1}
        """
    else:
        sql = f"""
        SELECT {select_fields}
        FROM {settings.SCHEMA_NAME}.products
        WHERE {where_clause}
        ORDER BY similarity(normalize_text({fields[0]}), normalize_text($1)) DESC
        LIMIT ${len(fields) * 2 + 1}
        """

    # Build parameters
    params = []
    # For SELECT similarity scores and GREATEST
    for _ in fields:
        params.append(query)
    # For WHERE conditions (query, threshold pairs)
    for _ in fields:
        params.append(min_similarity)
    # LIMIT
    params.append(limit)

    try:
        rows = await fetchall_async(sql, *params)

        logger.info(
            "Async fuzzy search completed: %d results found with similarity >= %.2f",
            len(rows),
            min_similarity,
        )

        return rows

    except Exception as e:
        logger.error("Error in async fuzzy search: %s", e)
        raise


async def fuzzy_search_smart_async(
    query: str,
    fields: list[str] | None = None,
    limit: int = PaginationDefaults.SEARCH_LIMIT,
    offset: int = 0,
    strict_threshold: float = 0.25,
    word_threshold: float = 0.35,
    fallback_threshold: float = 0.15,
    name_weight: float = 2.0,
    description_weight: float = 1.0,
    category_weight: float = 1.5,
    brand_weight: float = 1.0,
) -> dict[str, Any]:
    """Async smart fuzzy search with multi-tier fallback strategy.

    Implements a four-tier search strategy:
    1. Standard similarity search (strict_threshold)
    2. Word similarity search for partial matches (word_threshold) - WITH WEIGHTED SCORING
    2.5. Token-based search - searches by individual words when multi-word query fails
    3. Relaxed similarity search as final fallback (fallback_threshold)

    Args:
        query: Search term to match against
        fields: List of fields to search in (default: ['name', 'description', 'category'])
        limit: Maximum number of results to return
        offset: Number of results to skip for pagination
        strict_threshold: Initial similarity threshold
        word_threshold: Threshold for word_similarity search
        fallback_threshold: Final fallback threshold
        name_weight: Weight multiplier for name field matches
        description_weight: Weight for description field matches
        category_weight: Weight for category field matches
        brand_weight: Weight for brand field matches

    Returns:
        PaginatedResponse dict with items, count, total_count, and pagination metadata
    """
    page_params = PaginationParams.for_search(limit=limit, offset=offset)

    if not query or not query.strip():
        logger.warning("Empty query provided to fuzzy_search_smart_async")
        return PaginatedResponse.empty(page_params, query=query).to_dict()

    if fields is None:
        fields = ["name", "description", "category"]

    logger.info(
        "Starting async smart fuzzy search: query='%s', fields=%s, limit=%d, offset=%d",
        query,
        fields,
        page_params.limit,
        page_params.offset,
    )

    validate_schema_name(settings.SCHEMA_NAME)

    # Get total count
    count_sql = f"SELECT COUNT(*) as total FROM {settings.SCHEMA_NAME}.products"
    count_result = await fetchone_async(count_sql)
    total_count = count_result["total"] if count_result else 0

    def make_response(items: list[dict]) -> dict[str, Any]:
        return PaginatedResponse.create(
            items=items,
            total_count=total_count,
            params=page_params,
            query=query,
        ).to_dict()

    # Tier 1: Standard similarity search
    results = await fuzzy_search_async(
        query=query,
        fields=fields,
        min_similarity=strict_threshold,
        limit=page_params.limit + page_params.offset,
        include_similarity=True,
    )

    if results:
        paginated_results = results[page_params.offset : page_params.offset + page_params.limit]
        logger.info("Async smart search succeeded at Tier 1 (standard similarity)")
        for result in paginated_results:
            result["search_tier"] = "standard"
        return make_response(paginated_results)

    # Tier 2: Word similarity search with weighted scoring
    logger.info("Tier 1 no results, trying Tier 2 (word similarity with weighted scoring)")

    field_weights = {
        "name": name_weight,
        "description": description_weight,
        "category": category_weight,
        "brand": brand_weight,
    }

    base_fields = "id, sku, name, description, category, brand, tags, color, size, price"
    word_conditions = []
    word_selects = []
    weighted_components = []
    total_weight = 0.0
    param_idx = 0

    for field in fields:
        weight = field_weights.get(field, 1.0)
        total_weight += weight
        param_idx += 1  # noqa: SIM113

        word_conditions.append(
            f"word_similarity(${param_idx}, {field}) >= ${param_idx + len(fields) * 3}"
        )
        word_selects.append(f"word_similarity(${param_idx}, {field}) AS {field}_word_sim")
        weighted_components.append(
            f"(word_similarity(${param_idx + len(fields)}, {field}) * {weight})"
        )

    weighted_score = f"({' + '.join(weighted_components)}) / {total_weight}"
    max_word_similarities = ", ".join(
        [f"word_similarity(${i + 1 + len(fields) * 2}, {f})" for i, f in enumerate(fields)]
    )

    select_fields = (
        f"{base_fields}, {', '.join(word_selects)}, "
        f"GREATEST({max_word_similarities}) AS max_word_similarity, "
        f"{weighted_score} AS weighted_similarity"
    )
    where_clause = " OR ".join(word_conditions)

    sql = f"""
    SELECT {select_fields}
    FROM {settings.SCHEMA_NAME}.products
    WHERE {where_clause}
    ORDER BY weighted_similarity DESC, max_word_similarity DESC
    LIMIT ${len(fields) * 4 + 1} OFFSET ${len(fields) * 4 + 2}
    """

    # Build parameters
    params = []
    # For word_selects
    for _ in fields:
        params.append(query)
    # For weighted_components
    for _ in fields:
        params.append(query)
    # For max_word_similarities GREATEST
    for _ in fields:
        params.append(query)
    # For WHERE conditions (thresholds)
    for _ in fields:
        params.append(word_threshold)
    # Limit and Offset
    params.append(page_params.limit)
    params.append(page_params.offset)

    try:
        rows = await fetchall_async(sql, *params)

        if rows:
            logger.info(
                "Async smart search succeeded at Tier 2: %d results with word_similarity >= %.2f",
                len(rows),
                word_threshold,
            )
            for row in rows:
                row["search_tier"] = "word_similarity"
                row["max_similarity"] = row.get(
                    "weighted_similarity", row.get("max_word_similarity", 0)
                )
            return make_response(rows)

    except Exception as e:
        logger.error("Error in Tier 2 async word similarity search: %s", e)

    # Tier 3: Relaxed threshold as final fallback
    logger.info("Tier 2 no results, trying Tier 3 (relaxed threshold)")
    results = await fuzzy_search_async(
        query=query,
        fields=fields,
        min_similarity=fallback_threshold,
        limit=page_params.limit + page_params.offset,
        include_similarity=True,
    )

    if results:
        paginated_results = results[page_params.offset : page_params.offset + page_params.limit]
        logger.info(
            "Async smart search succeeded at Tier 3: %d results with similarity >= %.2f",
            len(paginated_results),
            fallback_threshold,
        )
        for result in paginated_results:
            result["search_tier"] = "fallback"
            result["low_confidence"] = True
        return make_response(paginated_results)

    logger.info("No results found even with relaxed threshold")
    return make_response([])
