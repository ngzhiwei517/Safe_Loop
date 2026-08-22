"""Append AI drafts with provider evidence and no mutation path."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import json
from typing import NoReturn
from uuid import UUID

import asyncpg
from asyncpg.pool import PoolConnectionProxy

from app.ai.intake_graph import DraftEnvelope, DraftPayload
from app.ai.validator import validate_draft
from app.db import connection


class DraftPersistenceError(Exception):
    """Carry a stable code for a refused or invalid draft write."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@asynccontextmanager
async def _draft_connection(
    existing: PoolConnectionProxy[asyncpg.Record] | None,
) -> AsyncIterator[PoolConnectionProxy[asyncpg.Record]]:
    if existing is not None:
        yield existing
        return
    async with connection() as conn:
        yield conn


def _draft_payload(envelope: DraftEnvelope) -> DraftPayload:
    return {
        "observed_facts": envelope["observed_facts"],
        "assumptions": envelope["assumptions"],
        "missing_information": envelope["missing_information"],
        "proposed_category": envelope["proposed_category"],
        "proposed_urgency": envelope["proposed_urgency"],
        "suggested_owner_role": envelope["suggested_owner_role"],
        "suggested_action": envelope["suggested_action"],
        "confidence": envelope["confidence"],
        "needs_escalation": envelope["needs_escalation"],
        "escalation_reason": envelope["escalation_reason"],
        "citations": envelope["citations"],
    }


def _assert_envelope(envelope: DraftEnvelope) -> DraftPayload:
    payload = _draft_payload(envelope)
    try:
        raw_payload = json.loads(envelope["raw"])
    except (TypeError, json.JSONDecodeError) as error:
        raise DraftPersistenceError(
            "draft_raw_invalid",
            "provider raw output is not valid JSON",
        ) from error
    if raw_payload != payload:
        raise DraftPersistenceError(
            "draft_raw_mismatch",
            "provider raw output does not match the structured draft",
        )
    return payload


async def _citation_sources(
    conn: PoolConnectionProxy[asyncpg.Record],
    payload: DraftPayload,
) -> list[dict[str, object]]:
    document_ids = list(
        dict.fromkeys(citation["document_id"] for citation in payload["citations"])
    )
    if not document_ids:
        return []
    rows = await conn.fetch(
        """
        select d.id::text as document_id,
               d.doc_ref,
               d.revision,
               dc.section,
               dc.page,
               dc.content
        from document_chunks dc
        join documents d on d.id = dc.document_id
        where d.id::text = any($1::text[])
          and d.is_approved = true
          and d.effective_from <= now()
        for share of d, dc
        """,
        document_ids,
    )
    return [dict(row) for row in rows]


async def append_draft(
    report_id: UUID,
    envelope: DraftEnvelope,
    *,
    transaction_connection: PoolConnectionProxy[asyncpg.Record] | None = None,
) -> asyncpg.Record:
    """Allocate the next version while holding the parent report lock."""
    payload = _assert_envelope(envelope)
    async with _draft_connection(transaction_connection) as conn:
        async with conn.transaction():
            locked_report_id = await conn.fetchval(
                "select id from reports where id = $1 for update",
                report_id,
            )
            if locked_report_id is None:
                raise DraftPersistenceError(
                    "report_not_found",
                    "report does not exist",
                )
            sources = await _citation_sources(conn, payload)
            validation, validation_errors = validate_draft(
                payload,
                citation_sources=sources,
            )
            version = await conn.fetchval(
                """
                select coalesce(max(version), 0) + 1
                from ai_drafts
                where report_id = $1
                """,
                report_id,
            )
            if not isinstance(version, int):
                raise RuntimeError("database returned an invalid draft version")
            draft = await conn.fetchrow(
                """
                insert into ai_drafts (
                  report_id, version, provider, provider_ref, raw_json,
                  observed_facts, assumptions, missing_information,
                  proposed_category, proposed_urgency, suggested_owner_role,
                  suggested_action, confidence, needs_escalation, escalation_reason,
                  citations, validation, validation_errors,
                  latency_ms, tokens_in, tokens_out
                )
                values (
                  $1, $2, $3, $4, $5::jsonb,
                  $6::jsonb, $7::jsonb, $8::jsonb,
                  $9, $10::urgency, $11::role,
                  $12, $13, $14, $15, $16::jsonb, $17::validation_status,
                  $18::jsonb, $19, $20, $21
                )
                returning *
                """,
                report_id,
                version,
                envelope["provider"],
                envelope["provider_ref"],
                envelope["raw"],
                json.dumps(payload["observed_facts"]),
                json.dumps(payload["assumptions"]),
                json.dumps(payload["missing_information"]),
                payload["proposed_category"],
                payload["proposed_urgency"],
                payload["suggested_owner_role"],
                payload["suggested_action"],
                payload["confidence"],
                payload["needs_escalation"],
                payload["escalation_reason"],
                json.dumps(payload["citations"]),
                validation.value,
                json.dumps(validation_errors),
                envelope["latency_ms"],
                envelope["tokens_in"],
                envelope["tokens_out"],
            )
            if draft is None:
                raise RuntimeError("database did not return the appended draft")
            return draft


async def update_draft(_draft_id: UUID, _changes: dict[str, object]) -> NoReturn:
    """Refuse mutation at the service boundary before SQL can be attempted."""
    raise DraftPersistenceError(
        "draft_append_only",
        "AI drafts cannot be updated",
    )
