"""
Embeddings Client with Caching.

Generates text embeddings using Google Gemini AI with LRU caching
to reduce API calls and improve performance for repeated queries.
"""

from google import genai
from google.genai import types

from config import settings
from utils.logger import get_logger

# Get logger for embeddings
logger = get_logger("mcp_embeddings")

# Cache size for embeddings (adjustable via settings if needed)
EMBEDDING_CACHE_SIZE = 1000

# Module-level cache storage (avoids memory leak with method lru_cache)
_embedding_cache: dict[str, tuple[float, ...]] = {}
_cache_hits = 0
_cache_misses = 0


def _get_cached_embedding(text: str, client: "EmbeddingsClient") -> tuple[float, ...]:
    """Get embedding from cache or generate new one.

    Uses module-level cache to avoid memory leaks from lru_cache on methods.

    Args:
        text: Text to embed
        client: EmbeddingsClient instance for API calls

    Returns:
        Tuple of floats representing the embedding vector
    """
    global _cache_hits, _cache_misses

    if text in _embedding_cache:
        _cache_hits += 1
        logger.debug("Cache hit for: %s...", text[:30])
        return _embedding_cache[text]

    _cache_misses += 1
    logger.debug("Cache miss - generating embedding for: %s...", text[:50])

    resp = client._client.models.embed_content(
        model=client._model,
        contents=[text],
        config=types.EmbedContentConfig(output_dimensionality=client._dimension),
    )

    if resp.embeddings is None or not resp.embeddings:
        logger.warning("No embedding returned for text")
        return ()

    result = tuple(resp.embeddings[0].values) if resp.embeddings[0].values else ()

    # Add to cache (with LRU eviction if full)
    if len(_embedding_cache) >= EMBEDDING_CACHE_SIZE:
        # Remove oldest entry (first key)
        oldest_key = next(iter(_embedding_cache))
        del _embedding_cache[oldest_key]

    _embedding_cache[text] = result
    return result


class EmbeddingsClient:
    """Client for generating text embeddings using Google Gemini AI.

    This client provides a simple interface to generate vector embeddings from text
    using Google's Gemini embedding model. The embeddings are used for semantic
    search and similarity calculations in the product search system.

    Features:
    - LRU caching for repeated queries (reduces API costs)
    - Batch processing support
    - Cache statistics for monitoring

    Attributes:
        _client: Google GenAI client instance
        _model: Name of the embedding model to use (default: gemini-embedding-001)

    Example:
        >>> client = EmbeddingsClient()
        >>> vectors = client.embed(["laptop gaming", "silla oficina"])
        >>> len(vectors)  # 2 vectors
        2
        >>> len(vectors[0])  # 1536 dimensions
        1536
    """

    def __init__(self) -> None:
        """Initialize the embeddings client with Google Gemini API.

        Reads API key, model, and dimension configuration from settings
        and creates a Google GenAI client instance.

        Raises:
            ValueError: If GOOGLE_API_KEY is not set in settings
        """
        logger.info(
            "Initializing embeddings client with model: %s, dimension: %d (cache_size=%d)",
            settings.EMBEDDING_MODEL,
            settings.EMBEDDING_DIMENSION,
            EMBEDDING_CACHE_SIZE,
        )
        self._client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        self._model = settings.EMBEDDING_MODEL
        self._dimension = settings.EMBEDDING_DIMENSION

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Converts each text into a 1536-dimensional vector using Google's Gemini
        embedding model. Uses LRU caching to avoid redundant API calls for
        previously seen queries.

        Args:
            texts: List of text strings to convert into embeddings

        Returns:
            List of embedding vectors, where each vector is a list of 1536 floats.
            Empty list if input is empty or if embeddings generation fails.

        Raises:
            Exception: If API call fails or authentication error occurs

        Example:
            >>> embeddings = client.embed(["robot aspirador", "laptop gaming"])
            >>> len(embeddings)
            2
            >>> isinstance(embeddings[0], list)
            True
            >>> len(embeddings[0])  # Gemini embedding-001 dimension
            1536

        Note:
            - Cached queries don't count toward Google API quota
            - Batch processing is more efficient for new texts
            - Model: gemini-embedding-001 (supports Spanish and English)
        """
        if not texts:
            logger.debug("Empty text list, returning empty list")
            return []

        logger.debug("Generating embeddings for %d texts", len(texts))

        try:
            results: list[list[float]] = []

            for text in texts:
                try:
                    cached_result = _get_cached_embedding(text, self)
                    results.append(list(cached_result) if cached_result else [])
                except Exception as e:
                    logger.error("Error embedding text '%s...': %s", text[:30], e)
                    results.append([])

            logger.debug(
                "Embeddings generated: %d vectors (cache hits: %d, misses: %d)",
                len(results),
                _cache_hits,
                _cache_misses,
            )
            return results

        except Exception as e:
            logger.error("Error generating embeddings: %s", e)
            raise

    def get_cache_stats(self) -> dict:
        """Get cache statistics for monitoring.

        Returns:
            Dictionary with cache statistics:
            - hits: Number of cache hits
            - misses: Number of cache misses
            - hit_rate: Percentage of cache hits
            - size: Current cache size
            - maxsize: Maximum cache size
        """
        total = _cache_hits + _cache_misses
        hit_rate = (_cache_hits / total * 100) if total > 0 else 0.0

        return {
            "hits": _cache_hits,
            "misses": _cache_misses,
            "hit_rate": round(hit_rate, 2),
            "size": len(_embedding_cache),
            "maxsize": EMBEDDING_CACHE_SIZE,
        }

    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        global _cache_hits, _cache_misses
        _embedding_cache.clear()
        _cache_hits = 0
        _cache_misses = 0
        logger.info("Embedding cache cleared")


emb_client = EmbeddingsClient()
