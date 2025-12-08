"""Direct product fetching by SKU and ID.

Provides fast direct lookups for products.
All operations are async for non-blocking database access.

Author: Odiseo Team
Version: 2.0.0
"""

from config import settings
from utils.db_async import fetchone_async
from utils.logger import get_logger
from utils.validation import validate_schema_name

# Get logger for fetch operations
logger = get_logger("mcp_tools_fetch")


async def fetch_by_sku_async(sku: str) -> dict | None:
    """Fetch a single product by exact SKU (Stock Keeping Unit) code.

    Performs direct database lookup using exact SKU matching. This is the fastest
    search method (~9ms average) and should be used when the client explicitly
    mentions a product code.

    Use cases:
    - "I want the TOY-0018"
    - "looking for product COMP-0038"
    - "give me info about SKU HOME-0007"

    Performance: ~9ms average (direct indexed lookup)

    Args:
        sku: Exact product SKU code (case-sensitive)
             Format examples: COMP-0009, TOY-0018, HOME-0007, AUTO-0016

    Returns:
        Product dict if found, None if not found
        Dict contains: {id, sku, name, description, category, brand, tags, color, size, price}

    Example:
        >>> await fetch_by_sku_async("TOY-0018")
        {'id': 18, 'sku': 'TOY-0018', 'name': 'Puzzle 1000 Piezas', ...}
        >>> await fetch_by_sku_async("INVALID-SKU")
        None
    """
    logger.debug("Searching product by SKU: %s", sku)
    validate_schema_name(settings.SCHEMA_NAME)

    sql = (
        f"SELECT id, sku, name, description, category, brand, tags, color, size, price "
        f"FROM {settings.SCHEMA_NAME}.products WHERE sku = $1"
    )
    result = await fetchone_async(sql, sku)

    if result:
        logger.debug("Product found by SKU %s: ID=%s", sku, result.get("id"))
    else:
        logger.warning("Product not found with SKU: %s", sku)

    return result


async def fetch_by_id_async(product_id: int) -> dict | None:
    """Fetch a single product by internal database ID.

    Performs direct database lookup using the product's primary key ID. Similar to
    fetch_by_sku but uses numeric ID instead of SKU code. Rarely used by end clients
    (they typically reference SKU codes), but useful for internal operations.

    Performance: ~9ms average (direct primary key lookup)

    Args:
        product_id: Database primary key ID (integer)

    Returns:
        Product dict if found, None if not found
        Dict contains: {id, sku, name, description, category, brand, tags, color, size, price}

    Example:
        >>> await fetch_by_id_async(18)
        {'id': 18, 'sku': 'TOY-0018', 'name': 'Puzzle 1000 Piezas', ...}
        >>> await fetch_by_id_async(9999)
        None
    """
    logger.debug("Searching product by ID: %s", product_id)
    validate_schema_name(settings.SCHEMA_NAME)

    sql = (
        f"SELECT id, sku, name, description, category, brand, tags, color, size, price "
        f"FROM {settings.SCHEMA_NAME}.products WHERE id = $1"
    )
    result = await fetchone_async(sql, product_id)

    if result:
        logger.debug("Product found by ID %s: SKU=%s", product_id, result.get("sku"))
    else:
        logger.warning("Product not found with ID: %s", product_id)

    return result
