"""Verify batching and retry semantics independently of document parsing and Postgres."""

from __future__ import annotations

import asyncio

from app.ai.provider import StubProvider, Vector
from app.rag.embeddings import embed_texts_batched


class FlakyEmbeddingProvider:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.failed_once = False
        self.stub = StubProvider()

    async def embed(self, texts: list[str]) -> list[Vector]:
        self.calls.append(texts)
        if not self.failed_once:
            self.failed_once = True
            raise RuntimeError("transient provider failure")
        return await self.stub.embed(texts)


def test_embedding_batches_retry_only_the_failed_batch() -> None:
    provider = FlakyEmbeddingProvider()
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    vectors = asyncio.run(
        embed_texts_batched(
            ["one", "two", "three", "four", "five"],
            provider=provider,
            batch_size=2,
            retry_delay_seconds=0.01,
            sleep=record_sleep,
        )
    )

    assert provider.calls == [
        ["one", "two"],
        ["one", "two"],
        ["three", "four"],
        ["five"],
    ]
    assert delays == [0.01]
    assert len(vectors) == 5


def test_empty_embedding_input_does_not_call_the_provider() -> None:
    provider = FlakyEmbeddingProvider()

    assert asyncio.run(embed_texts_batched([], provider=provider)) == []
    assert provider.calls == []
