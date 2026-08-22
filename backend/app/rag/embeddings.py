"""Generate and serialise embeddings without coupling corpus code to one provider."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from math import isfinite

from app.ai.provider import AIProvider, EMBEDDING_DIMENSIONS, Vector, get_provider

AsyncSleep = Callable[[float], Awaitable[None]]


class EmbeddingGenerationError(RuntimeError):
    """Fail ingest when a provider cannot return complete, valid vectors."""


def _validate_vectors(vectors: list[Vector], expected_count: int) -> None:
    if len(vectors) != expected_count:
        raise EmbeddingGenerationError("embedding provider returned the wrong vector count")
    if any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
        raise EmbeddingGenerationError("embedding provider returned the wrong dimensions")
    if any(not isfinite(value) for vector in vectors for value in vector):
        raise EmbeddingGenerationError("embedding provider returned a non-finite value")


async def embed_texts_batched(
    texts: Sequence[str],
    *,
    provider: AIProvider | None = None,
    batch_size: int = 32,
    max_attempts: int = 3,
    retry_delay_seconds: float = 0.05,
    sleep: AsyncSleep = asyncio.sleep,
) -> list[Vector]:
    """Embed bounded batches, retrying one failed batch without repeating prior work."""
    if batch_size <= 0 or max_attempts <= 0 or retry_delay_seconds < 0:
        raise ValueError("embedding retry settings are invalid")
    if not texts:
        return []
    active_provider = provider or get_provider()
    result: list[Vector] = []
    for offset in range(0, len(texts), batch_size):
        batch = list(texts[offset : offset + batch_size])
        for attempt in range(max_attempts):
            try:
                vectors = await active_provider.embed(batch)
                _validate_vectors(vectors, len(batch))
            except Exception as error:
                if attempt + 1 == max_attempts:
                    raise EmbeddingGenerationError(
                        "embedding provider failed after retries"
                    ) from error
                await sleep(retry_delay_seconds * (2**attempt))
            else:
                result.extend(vectors)
                break
    return result


def vector_literal(vector: Sequence[float]) -> str:
    """Create pgvector's text input form after enforcing the corpus dimensions."""
    values = list(vector)
    _validate_vectors([values], 1)
    return "[" + ",".join(format(value, ".10g") for value in values) + "]"
