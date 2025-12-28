"""
Async Database Module - Fully asynchronous PostgreSQL operations.

Uses asyncpg for non-blocking database operations, improving performance
in async MCP handlers by not blocking the event loop.

Usage:
    from utils.db_async import init_db_async, fetchone_async, fetchall_async

    # Initialize at startup
    await init_db_async()

    # Use async functions
    result = await fetchone_async("SELECT * FROM products WHERE id = $1", 42)
    results = await fetchall_async("SELECT * FROM products WHERE category = $1", "Electronics")

Note:
    - Uses $1, $2, etc. for parameters (asyncpg style) instead of %s
    - Maintains same return format as sync db.py (dict/list[dict])
"""

import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from pgvector.asyncpg import register_vector

from config import settings
from utils.logger import get_logger

logger = get_logger("mcp_db_async")

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def init_db_async(min_size: int = 1, max_size: int = 10) -> None:
    """Initialize async database connection pool.

    Creates an asyncpg connection pool with pgvector support.
    Thread-safe initialization using asyncio.Lock.

    Args:
        min_size: Minimum pool connections (default: 1)
        max_size: Maximum pool connections (default: 10)
    """
    global _pool

    async with _pool_lock:
        if _pool is not None:
            return

        try:
            logger.info("Initializing async database connection pool...")

            async def init_connection(conn: asyncpg.Connection) -> None:
                """Initialize each connection with pgvector.

                Raises:
                    Exception: If pgvector extension is not installed
                """
                await register_vector(conn)

            _pool = await asyncpg.create_pool(
                dsn=settings.DATABASE_URL,
                min_size=min_size,
                max_size=max_size,
                init=init_connection,
                command_timeout=60,
            )

            logger.info(
                "Async database pool initialized successfully (min=%d, max=%d)", min_size, max_size
            )

        except Exception as e:
            logger.error("Failed to initialize async database pool: %s", e)
            raise


async def close_db_async() -> None:
    """Close the async database pool."""
    global _pool

    async with _pool_lock:
        if _pool is not None:
            await _pool.close()
            _pool = None
            logger.info("Async database pool closed")


async def get_pool() -> asyncpg.Pool:
    """Get the connection pool, initializing if needed."""
    if _pool is None:
        await init_db_async()
    assert _pool is not None
    return _pool


@asynccontextmanager
async def get_conn_async() -> AsyncIterator[asyncpg.Connection]:
    """Async context manager for database connection with transaction support.

    Provides a connection from the pool for operations that require
    manual transaction control (BEGIN, COMMIT, ROLLBACK).

    Yields:
        asyncpg.Connection: Database connection from the pool

    Example:
        >>> async with get_conn_async() as conn:
        ...     async with conn.transaction():
        ...         await conn.execute("INSERT INTO ...")
        ...         await conn.execute("UPDATE ...")
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def fetchone_async(
    query: str,
    *args: Any,
    timeout: float | None = None,
) -> dict[str, Any] | None:
    """Execute a query and return a single row as a dictionary.

    Args:
        query: SQL query with $1, $2, ... placeholders
        *args: Query parameters (positional)
        timeout: Query timeout in seconds (optional)

    Returns:
        Dictionary with column names as keys, or None if no row found

    Example:
        >>> result = await fetchone_async("SELECT * FROM products WHERE id = $1", 42)
        >>> if result:
        ...     print(result['name'])
    """
    pool = await get_pool()
    max_retries = 2

    for attempt in range(max_retries):
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, *args, timeout=timeout)
                return dict(row) if row else None

        except asyncpg.PostgresConnectionError as e:
            if attempt < max_retries - 1:
                logger.warning(
                    "Async DB connection error, retrying (attempt %d/%d): %s",
                    attempt + 1,
                    max_retries,
                    e,
                )
                await asyncio.sleep(0.1)  # Brief delay before retry
                continue
            logger.exception("Async fetchone failed after retries")
            raise

        except Exception:
            logger.exception("Async fetchone query failed")
            raise

    return None


async def fetchall_async(
    query: str,
    *args: Any,
    timeout: float | None = None,
) -> list[dict[str, Any]]:
    """Execute a query and return all rows as a list of dictionaries.

    Args:
        query: SQL query with $1, $2, ... placeholders
        *args: Query parameters (positional)
        timeout: Query timeout in seconds (optional)

    Returns:
        List of dictionaries, each representing a row

    Example:
        >>> results = await fetchall_async(
        ...     "SELECT * FROM products WHERE category = $1",
        ...     "Electronics"
        ... )
        >>> for product in results:
        ...     print(product['name'])
    """
    pool = await get_pool()
    max_retries = 2

    for attempt in range(max_retries):
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(query, *args, timeout=timeout)
                return [dict(row) for row in rows]

        except asyncpg.PostgresConnectionError as e:
            if attempt < max_retries - 1:
                logger.warning(
                    "Async DB connection error, retrying (attempt %d/%d): %s",
                    attempt + 1,
                    max_retries,
                    e,
                )
                await asyncio.sleep(0.1)
                continue
            logger.exception("Async fetchall failed after retries")
            raise

        except Exception:
            logger.exception("Async fetchall query failed")
            raise

    return []


async def execute_async(
    query: str,
    *args: Any,
    timeout: float | None = None,
) -> str:
    """Execute a query without returning results (INSERT, UPDATE, DELETE).

    Args:
        query: SQL query with $1, $2, ... placeholders
        *args: Query parameters (positional)
        timeout: Query timeout in seconds (optional)

    Returns:
        Status string from PostgreSQL (e.g., "UPDATE 1", "DELETE 3")

    Example:
        >>> await execute_async("UPDATE products SET price = $1 WHERE id = $2", 99.99, 42)
        >>> await execute_async("DELETE FROM products WHERE sku = $1", "OLD-001")
    """
    pool = await get_pool()
    max_retries = 2

    for attempt in range(max_retries):
        try:
            async with pool.acquire() as conn:
                result = await conn.execute(query, *args, timeout=timeout)
                return result

        except asyncpg.PostgresConnectionError as e:
            if attempt < max_retries - 1:
                logger.warning(
                    "Async DB connection error, retrying (attempt %d/%d): %s",
                    attempt + 1,
                    max_retries,
                    e,
                )
                await asyncio.sleep(0.1)
                continue
            logger.exception("Async execute failed after retries")
            raise

        except Exception:
            logger.exception("Async execute query failed")
            raise

    return ""


async def executemany_async(
    query: str,
    args_list: list[tuple[Any, ...]],
    timeout: float | None = None,
) -> None:
    """Execute a query multiple times with different parameters.

    Args:
        query: SQL query with $1, $2, ... placeholders
        args_list: List of parameter tuples
        timeout: Query timeout in seconds (optional)

    Example:
        >>> await executemany_async(
        ...     "INSERT INTO products (name, price) VALUES ($1, $2)",
        ...     [("Product A", 10.00), ("Product B", 20.00)]
        ... )
    """
    pool = await get_pool()

    try:
        async with pool.acquire() as conn:
            await conn.executemany(query, args_list, timeout=timeout)

    except Exception:
        logger.exception("Async executemany query failed")
        raise


def convert_query_placeholders(query: str) -> str:
    """Convert %s placeholders to $1, $2, etc. for asyncpg compatibility.

    Utility function to help migrate queries from psycopg2 format.

    Args:
        query: SQL query with %s placeholders

    Returns:
        Query with $1, $2, ... placeholders

    Example:
        >>> convert_query_placeholders("SELECT * FROM t WHERE a = %s AND b = %s")
        'SELECT * FROM t WHERE a = $1 AND b = $2'
    """
    counter = [0]  # Use list for closure mutability

    def replacer(match: re.Match) -> str:
        counter[0] += 1
        return f"${counter[0]}"

    return re.sub(r"%s", replacer, query)
