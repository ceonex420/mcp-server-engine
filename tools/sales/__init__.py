"""Sales Tools Module.

This module contains product search and retrieval functionality:
- fetch: Direct SKU and ID lookups
- search: Semantic vector search using embeddings
- fuzzy_search: Typo-tolerant text matching

All functions are async for non-blocking I/O using asyncpg.

Author: Odiseo Team
Version: 2.0.0
"""

from tools.sales.embedding_search import search_products_by_embedding_async
from tools.sales.fetch import (
    fetch_by_id_async,
    fetch_by_sku_async,
)
from tools.sales.fuzzy_search import (
    fuzzy_search_async,
    fuzzy_search_smart_async,
)
from tools.sales.search import search_products_async

__all__ = [
    "fetch_by_id_async",
    "fetch_by_sku_async",
    "fuzzy_search_async",
    "fuzzy_search_smart_async",
    "search_products_async",
    "search_products_by_embedding_async",
]
