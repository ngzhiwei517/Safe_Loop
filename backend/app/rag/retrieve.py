"""Retrieve only current human-approved procedure chunks by cosine similarity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from app.ai.provider import AIProvider
from app.db import connection
from app.rag.embeddings import embed_texts_batched, vector_literal

DEFAULT_TOP_K = 6
DEFAULT_SIMILARITY_FLOOR = 0.35
IVFFLAT_PROBES = 10
IVFFLAT_MAX_PROBES = 100


@dataclass(frozen=True)
class RetrievedChunk:
    """Return the verbatim content and exact coordinates needed for a citation."""

    content: str
    document_id: UUID
    doc_ref: str
    revision: str
    section: str | None
    page: int | None
    similarity: float


async def retrieve_chunks(
    query: str,
    *,
    provider: AIProvider | None = None,
    top_k: int = DEFAULT_TOP_K,
    similarity_floor: float = DEFAULT_SIMILARITY_FLOOR,
) -> list[RetrievedChunk]:
    """Rank effective approved chunks and discard every result below the floor."""
    clean_query = query.strip()
    if not clean_query:
        return []
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if not 0.0 <= similarity_floor <= 1.0:
        raise ValueError("similarity_floor must be between zero and one")
    query_vector = (
        await embed_texts_batched([clean_query], provider=provider, batch_size=1)
    )[0]
    literal = vector_literal(query_vector)
    async with connection() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                select set_config('ivfflat.probes', $1, true),
                       set_config('ivfflat.iterative_scan', 'relaxed_order', true),
                       set_config('ivfflat.max_probes', $2, true)
                """,
                str(IVFFLAT_PROBES),
                str(IVFFLAT_MAX_PROBES),
            )
            rows = await conn.fetch(
                """
                select dc.content,
                       d.id as document_id,
                       d.doc_ref,
                       d.revision,
                       dc.section,
                       dc.page,
                       1 - (dc.embedding <=> $1::vector(1536)) as similarity
                from document_chunks dc
                join documents d on d.id = dc.document_id
                where d.is_approved = true
                  and d.effective_from <= now()
                  and dc.embedding is not null
                  and 1 - (dc.embedding <=> $1::vector(1536)) >= $2
                order by dc.embedding <=> $1::vector(1536), dc.id
                limit $3
                """,
                literal,
                similarity_floor,
                top_k,
            )
    results = [
        RetrievedChunk(
            content=cast(str, row["content"]),
            document_id=cast(UUID, row["document_id"]),
            doc_ref=cast(str, row["doc_ref"]),
            revision=cast(str, row["revision"]),
            section=cast(str | None, row["section"]),
            page=cast(int | None, row["page"]),
            similarity=float(row["similarity"]),
        )
        for row in rows
    ]
    return sorted(results, key=lambda result: result.similarity, reverse=True)
