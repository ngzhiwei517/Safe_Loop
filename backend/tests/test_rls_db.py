"""Prove the PostgreSQL role matrix without using the service role."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Final
from uuid import UUID, uuid4

import asyncpg
import pytest

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")

REPORTER_ID: Final = UUID("00000000-0000-0000-0000-000000000001")
OTHER_REPORTER_ID: Final = UUID("00000000-0000-0000-0000-000000000002")
REVIEWER_ID: Final = UUID("00000000-0000-0000-0000-000000000003")
RESPONSIBLE_ID: Final = UUID("00000000-0000-0000-0000-000000000004")
CREW_ID: Final = UUID("00000000-0000-0000-0000-000000000005")
ADMIN_ID: Final = UUID("00000000-0000-0000-0000-000000000006")

PROFILE_IDS: Final = (
    REPORTER_ID,
    OTHER_REPORTER_ID,
    REVIEWER_ID,
    RESPONSIBLE_ID,
    CREW_ID,
    ADMIN_ID,
)

REPORT_CHILD_TABLES: Final = (
    "report_media",
    "transcripts",
    "clarifications",
    "ai_drafts",
    "review_decisions",
    "report_assignments",
    "corrective_actions",
    "verifications",
    "audit_log",
)

RLS_TABLES: Final = (
    "profiles",
    "reports",
    *REPORT_CHILD_TABLES,
    "documents",
    "document_chunks",
    "briefings",
    "quiz_questions",
    "quiz_responses",
    "notifications",
    "alerts",
    "closure_receipts",
    "quiz_rate_limits",
    "request_rate_limits",
)

EXPECTED_POLICIES: Final = {
    ("profiles", "profiles_select_visible", "SELECT"),
    ("profiles", "profiles_update_own_language", "UPDATE"),
    ("reports", "reports_select_visible", "SELECT"),
    ("report_media", "report_media_select_visible_report", "SELECT"),
    ("transcripts", "transcripts_select_visible_report", "SELECT"),
    ("clarifications", "clarifications_select_visible_report", "SELECT"),
    ("ai_drafts", "ai_drafts_select_visible_report", "SELECT"),
    ("review_decisions", "review_decisions_select_visible_report", "SELECT"),
    ("report_assignments", "report_assignments_select_visible_report", "SELECT"),
    ("corrective_actions", "corrective_actions_select_visible_report", "SELECT"),
    ("verifications", "verifications_select_visible_report", "SELECT"),
    ("audit_log", "audit_log_select_visible_report", "SELECT"),
    ("closure_receipts", "closure_receipts_select_visible", "SELECT"),
    ("documents", "documents_select_authenticated", "SELECT"),
    ("documents", "documents_write_reviewers", "ALL"),
    ("document_chunks", "document_chunks_select_authenticated", "SELECT"),
    ("document_chunks", "document_chunks_write_reviewers", "ALL"),
    ("briefings", "briefings_select_visible", "SELECT"),
    ("briefings", "briefings_write_reviewers", "ALL"),
    ("quiz_questions", "quiz_questions_select_visible", "SELECT"),
    ("quiz_questions", "quiz_questions_write_reviewers", "ALL"),
    ("quiz_responses", "quiz_responses_select_own_or_reviewer", "SELECT"),
    ("notifications", "notifications_select_recipient", "SELECT"),
    ("notifications", "notifications_update_recipient", "UPDATE"),
    ("alerts", "alerts_select_visible", "SELECT"),
    ("alerts", "alerts_insert_own_report", "INSERT"),
    ("alerts", "alerts_update_reviewers", "UPDATE"),
}


@dataclass(frozen=True)
class MatrixRows:
    own_report: UUID
    other_report: UUID
    own_rows: dict[str, UUID]
    other_rows: dict[str, UUID]
    own_receipt: UUID
    other_receipt: UUID
    document: UUID
    chunk: UUID
    draft_briefing: UUID
    published_briefing: UUID
    draft_question: UUID
    published_question: UUID
    crew_response: UUID
    reporter_response: UUID
    own_notification: UUID
    other_notification: UUID
    own_alert: UUID
    other_alert: UUID


async def connect() -> asyncpg.Connection[asyncpg.Record]:
    assert DATABASE_URL is not None
    return await asyncpg.connect(DATABASE_URL)


async def assume_user(
    conn: asyncpg.Connection[asyncpg.Record], profile_id: UUID
) -> None:
    await conn.execute("reset role")
    claims = json.dumps({"sub": str(profile_id), "role": "authenticated"})
    await conn.execute(
        "select set_config('request.jwt.claim.sub', $1, true)", str(profile_id)
    )
    await conn.execute("select set_config('request.jwt.claims', $1, true)", claims)
    await conn.execute("set local role authenticated")
    assert await conn.fetchval("select current_user") == "authenticated"


async def assume_anon(conn: asyncpg.Connection[asyncpg.Record]) -> None:
    await conn.execute("reset role")
    await conn.execute("select set_config('request.jwt.claim.sub', '', true)")
    await conn.execute("select set_config('request.jwt.claims', '{}', true)")
    await conn.execute("set local role anon")


async def expect_denied(
    conn: asyncpg.Connection[asyncpg.Record], query: str, *args: object
) -> None:
    savepoint = conn.transaction()
    await savepoint.start()
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(query, *args)
    finally:
        await savepoint.rollback()


async def insert_report(
    conn: asyncpg.Connection[asyncpg.Record],
    reporter_id: UUID,
    *,
    confidential: bool,
) -> UUID:
    return await conn.fetchval(
        """
        insert into public.reports (
          reporter_id, description_original, location_text, activity, is_confidential
        ) values ($1, 'RLS fixture report', 'Zone RLS', 'Testing', $2)
        returning id
        """,
        reporter_id,
        confidential,
    )


async def seed_matrix(conn: asyncpg.Connection[asyncpg.Record]) -> MatrixRows:
    own_report = await insert_report(conn, REPORTER_ID, confidential=True)
    other_report = await insert_report(conn, OTHER_REPORTER_ID, confidential=False)

    own_media = await conn.fetchval(
        """
        insert into public.report_media (
          report_id, storage_path, mime_type, phase, caption
        ) values ($1, $2, 'image/jpeg', 'original', 'own')
        returning id
        """,
        own_report,
        f"{REPORTER_ID}/{own_report}/{uuid4()}.jpg",
    )
    other_media = await conn.fetchval(
        """
        insert into public.report_media (
          report_id, storage_path, mime_type, phase, caption
        ) values ($1, $2, 'image/jpeg', 'original', 'other')
        returning id
        """,
        other_report,
        f"{OTHER_REPORTER_ID}/{other_report}/{uuid4()}.jpg",
    )
    own_transcript = await conn.fetchval(
        """
        insert into public.transcripts (media_id, report_id, provider, model, text_raw)
        values ($1, $2, 'stub', 'stub-transcription', 'own transcript') returning id
        """,
        own_media,
        own_report,
    )
    other_transcript = await conn.fetchval(
        """
        insert into public.transcripts (media_id, report_id, provider, model, text_raw)
        values ($1, $2, 'stub', 'stub-transcription', 'other transcript') returning id
        """,
        other_media,
        other_report,
    )

    own_clarification = await conn.fetchval(
        """
        insert into public.clarifications (report_id, round, question, gap)
        values ($1, 1, 'Own question', 'own gap') returning id
        """,
        own_report,
    )
    other_clarification = await conn.fetchval(
        """
        insert into public.clarifications (report_id, round, question, gap)
        values ($1, 1, 'Other question', 'other gap') returning id
        """,
        other_report,
    )

    own_draft = await conn.fetchval(
        """
        insert into public.ai_drafts (
          report_id, version, provider, provider_ref, raw_json, observed_facts,
          assumptions, missing_information
        ) values (
          $1, 1, 'stub', $2, '{}'::jsonb, '["own fact"]'::jsonb,
          '[]'::jsonb, '[]'::jsonb
        ) returning id
        """,
        own_report,
        f"rls-{uuid4()}",
    )
    other_draft = await conn.fetchval(
        """
        insert into public.ai_drafts (
          report_id, version, provider, provider_ref, raw_json, observed_facts,
          assumptions, missing_information
        ) values (
          $1, 1, 'stub', $2, '{}'::jsonb, '["other fact"]'::jsonb,
          '[]'::jsonb, '[]'::jsonb
        ) returning id
        """,
        other_report,
        f"rls-{uuid4()}",
    )

    own_decision = await conn.fetchval(
        """
        insert into public.review_decisions (report_id, reviewer_id, decision)
        values ($1, $2, 'approve') returning id
        """,
        own_report,
        REVIEWER_ID,
    )
    other_decision = await conn.fetchval(
        """
        insert into public.review_decisions (report_id, reviewer_id, decision)
        values ($1, $2, 'approve') returning id
        """,
        other_report,
        REVIEWER_ID,
    )

    own_assignment = await conn.fetchval(
        """
        insert into public.report_assignments (
          report_id, assignee_id, case_role, due_at, active
        ) values ($1, $2, 'responsible', now() + interval '1 day', true)
        returning id
        """,
        own_report,
        RESPONSIBLE_ID,
    )
    other_assignment = await conn.fetchval(
        """
        insert into public.report_assignments (
          report_id, assignee_id, case_role, due_at, active
        ) values ($1, $2, 'responsible', now() + interval '1 day', false)
        returning id
        """,
        other_report,
        RESPONSIBLE_ID,
    )

    own_action = await conn.fetchval(
        """
        insert into public.corrective_actions (
          report_id, assignment_id, action_text, due_at
        ) values ($1, $2, 'Own action', now() + interval '1 day') returning id
        """,
        own_report,
        own_assignment,
    )
    other_action = await conn.fetchval(
        """
        insert into public.corrective_actions (
          report_id, assignment_id, action_text, due_at
        ) values ($1, $2, 'Other action', now() + interval '1 day') returning id
        """,
        other_report,
        other_assignment,
    )

    own_verification = await conn.fetchval(
        """
        insert into public.verifications (
          report_id, corrective_action_id, reviewer_id, passed, notes
        ) values ($1, $2, $3, true, 'Own verified') returning id
        """,
        own_report,
        own_action,
        REVIEWER_ID,
    )
    other_verification = await conn.fetchval(
        """
        insert into public.verifications (
          report_id, corrective_action_id, reviewer_id, passed, notes
        ) values ($1, $2, $3, true, 'Other verified') returning id
        """,
        other_report,
        other_action,
        REVIEWER_ID,
    )

    own_audit = await conn.fetchval(
        """
        insert into public.audit_log (
          report_id, actor_type, actor_id, event, metadata
        ) values ($1, 'human', $2, 'rls_own', '{}'::jsonb) returning id
        """,
        own_report,
        REPORTER_ID,
    )
    other_audit = await conn.fetchval(
        """
        insert into public.audit_log (
          report_id, actor_type, actor_id, event, metadata
        ) values ($1, 'human', $2, 'rls_other', '{}'::jsonb) returning id
        """,
        other_report,
        OTHER_REPORTER_ID,
    )
    await conn.execute(
        """
        insert into public.audit_log (actor_type, actor_id, event, metadata)
        values ('system', null, 'rls_global', '{}'::jsonb)
        """
    )

    own_receipt = await conn.fetchval(
        """
        insert into public.closure_receipts (
          report_id, verification_id, corrective_action_id, reporter_id,
          reporter_locale, action_text, verification_notes, verified_by_id,
          verified_by_name
        ) values (
          $1, $2, $3, $4, 'en', 'Own action', 'Own verified', $5, 'Reviewer'
        ) returning id
        """,
        own_report,
        own_verification,
        own_action,
        REPORTER_ID,
        REVIEWER_ID,
    )
    other_receipt = await conn.fetchval(
        """
        insert into public.closure_receipts (
          report_id, verification_id, corrective_action_id, reporter_id,
          reporter_locale, action_text, verification_notes, verified_by_id,
          verified_by_name
        ) values (
          $1, $2, $3, $4, 'zh-CN', 'Other action', 'Other verified', $5, 'Reviewer'
        ) returning id
        """,
        other_report,
        other_verification,
        other_action,
        OTHER_REPORTER_ID,
        REVIEWER_ID,
    )

    document = await conn.fetchval(
        """
        insert into public.documents (
          title, doc_ref, revision, is_approved, effective_from, storage_path,
          mime_type, uploaded_by, approved_by, approved_at
        ) values (
          'RLS procedure', $1, '1', true, now() - interval '1 day', $2,
          'application/pdf', $3, $3, now()
        ) returning id
        """,
        f"RLS-{uuid4()}",
        f"rls/{uuid4()}.pdf",
        REVIEWER_ID,
    )
    chunk = await conn.fetchval(
        """
        insert into public.document_chunks (
          document_id, section, page, content, chunk_index
        ) values ($1, '1', 1, 'Approved safety procedure.', 0) returning id
        """,
        document,
    )

    draft_briefing = await conn.fetchval(
        """
        insert into public.briefings (report_id, version, body, status)
        values (
          $1, 1, '{"en":"Draft lesson","zh-CN":"草稿课程"}'::jsonb, 'draft'
        ) returning id
        """,
        own_report,
    )
    published_briefing = await conn.fetchval(
        """
        insert into public.briefings (
          report_id, version, body, status, valid_from, valid_to, qr_token,
          approved_by, approved_at
        ) values (
          $1, 1, '{"en":"Published lesson","zh-CN":"已发布课程"}'::jsonb,
          'published', now() - interval '1 day', now() + interval '30 days',
          $2, $3, now()
        ) returning id
        """,
        other_report,
        f"rls-token-{uuid4().hex}",
        REVIEWER_ID,
    )

    options = json.dumps(
        [
            {"en": "One", "zh-CN": "一"},
            {"en": "Two", "zh-CN": "二"},
            {"en": "Three", "zh-CN": "三"},
            {"en": "Four", "zh-CN": "四"},
        ]
    )
    draft_question = await conn.fetchval(
        """
        insert into public.quiz_questions (
          briefing_id, position, question, explanation, options, correct_option
        ) values (
          $1, 1, '{"en":"Draft?","zh-CN":"草稿？"}'::jsonb,
          '{"en":"Draft explanation","zh-CN":"草稿说明"}'::jsonb,
          $2::jsonb, 0
        ) returning id
        """,
        draft_briefing,
        options,
    )
    published_question = await conn.fetchval(
        """
        insert into public.quiz_questions (
          briefing_id, position, question, explanation, options, correct_option
        ) values (
          $1, 1, '{"en":"Published?","zh-CN":"已发布？"}'::jsonb,
          '{"en":"Published explanation","zh-CN":"已发布说明"}'::jsonb,
          $2::jsonb, 0
        ) returning id
        """,
        published_briefing,
        options,
    )

    crew_response = await conn.fetchval(
        """
        insert into public.quiz_responses (
          question_id, respondent_id, selected_option, is_correct
        ) values ($1, $2, 0, true) returning id
        """,
        published_question,
        CREW_ID,
    )
    reporter_response = await conn.fetchval(
        """
        insert into public.quiz_responses (
          question_id, respondent_id, selected_option, is_correct
        ) values ($1, $2, 1, false) returning id
        """,
        published_question,
        REPORTER_ID,
    )

    own_notification = await conn.fetchval(
        """
        insert into public.notifications (
          recipient_id, kind, entity_type, entity_id, payload
        ) values ($1, 'assigned', 'report', $2, '{}'::jsonb) returning id
        """,
        REPORTER_ID,
        own_report,
    )
    other_notification = await conn.fetchval(
        """
        insert into public.notifications (
          recipient_id, kind, entity_type, entity_id, payload
        ) values ($1, 'assigned', 'report', $2, '{}'::jsonb) returning id
        """,
        OTHER_REPORTER_ID,
        other_report,
    )

    own_alert = await conn.fetchval(
        """
        insert into public.alerts (report_id, raised_by, location_text)
        values ($1, $2, 'Own alert') returning id
        """,
        own_report,
        REPORTER_ID,
    )
    other_alert = await conn.fetchval(
        """
        insert into public.alerts (report_id, raised_by, location_text)
        values ($1, $2, 'Other alert') returning id
        """,
        other_report,
        OTHER_REPORTER_ID,
    )

    return MatrixRows(
        own_report=own_report,
        other_report=other_report,
        own_rows={
            "report_media": own_media,
            "transcripts": own_transcript,
            "clarifications": own_clarification,
            "ai_drafts": own_draft,
            "review_decisions": own_decision,
            "report_assignments": own_assignment,
            "corrective_actions": own_action,
            "verifications": own_verification,
            "audit_log": own_audit,
        },
        other_rows={
            "report_media": other_media,
            "transcripts": other_transcript,
            "clarifications": other_clarification,
            "ai_drafts": other_draft,
            "review_decisions": other_decision,
            "report_assignments": other_assignment,
            "corrective_actions": other_action,
            "verifications": other_verification,
            "audit_log": other_audit,
        },
        own_receipt=own_receipt,
        other_receipt=other_receipt,
        document=document,
        chunk=chunk,
        draft_briefing=draft_briefing,
        published_briefing=published_briefing,
        draft_question=draft_question,
        published_question=published_question,
        crew_response=crew_response,
        reporter_response=reporter_response,
        own_notification=own_notification,
        other_notification=other_notification,
        own_alert=own_alert,
        other_alert=other_alert,
    )


async def fetch_ids(
    conn: asyncpg.Connection[asyncpg.Record], table: str, ids: tuple[UUID, ...]
) -> set[UUID]:
    assert table in RLS_TABLES
    rows = await conn.fetch(
        f"select id from public.{table} where id = any($1::uuid[])", list(ids)
    )
    return {row["id"] for row in rows}


def test_rls_is_enabled_and_grants_are_closed_by_default() -> None:
    async def check() -> None:
        conn = await connect()
        try:
            rls_rows = await conn.fetch(
                """
                select c.relname, c.relrowsecurity
                from pg_class as c
                join pg_namespace as n on n.oid = c.relnamespace
                where n.nspname = 'public' and c.relname = any($1::text[])
                """,
                list(RLS_TABLES),
            )
            assert {row["relname"] for row in rls_rows} == set(RLS_TABLES)
            assert all(row["relrowsecurity"] for row in rls_rows)

            policies = await conn.fetch(
                """
                select tablename, policyname, cmd, roles
                from pg_policies
                where schemaname = 'public'
                """
            )
            relevant = {
                (row["tablename"], row["policyname"], row["cmd"])
                for row in policies
                if row["tablename"] in RLS_TABLES
            }
            assert relevant == EXPECTED_POLICIES
            assert all(
                row["roles"] == ["authenticated"]
                for row in policies
                if row["tablename"] in RLS_TABLES
            )

            anon_grants = await conn.fetchval(
                """
                select count(*)
                from information_schema.role_table_grants
                where table_schema = 'public'
                  and table_name = any($1::text[])
                  and grantee = 'anon'
                """,
                list(RLS_TABLES),
            )
            assert anon_grants == 0

            reporter_id_granted = await conn.fetchval(
                """
                select has_column_privilege(
                  'authenticated', 'public.reports', 'reporter_id', 'select'
                )
                """
            )
            assert reporter_id_granted is False

            view_exists = await conn.fetchval(
                "select to_regclass('public.reports_visible') is not null"
            )
            assert view_exists is True

            anon_helper_access = await conn.fetchval(
                """
                select has_function_privilege(
                  'anon', 'public.safeloop_can_read_report(uuid)', 'execute'
                )
                """
            )
            assert anon_helper_access is False
        finally:
            await conn.close()

    asyncio.run(check())


def test_report_data_read_matrix_blocks_every_cross_role_read() -> None:
    async def check() -> None:
        conn = await connect()
        transaction = conn.transaction()
        await transaction.start()
        try:
            data = await seed_matrix(conn)
            reports = (data.own_report, data.other_report)
            role_expectations = {
                REPORTER_ID: {data.own_report},
                OTHER_REPORTER_ID: {data.other_report},
                REVIEWER_ID: set(reports),
                RESPONSIBLE_ID: {data.own_report},
                CREW_ID: set(),
                ADMIN_ID: set(reports),
            }

            for profile_id, expected in role_expectations.items():
                await assume_user(conn, profile_id)
                assert await fetch_ids(conn, "reports", reports) == expected
                for table in REPORT_CHILD_TABLES:
                    ids = (data.own_rows[table], data.other_rows[table])
                    expected_rows = {
                        row_id
                        for report_id, row_id in zip(reports, ids, strict=True)
                        if report_id in expected
                    }
                    assert await fetch_ids(conn, table, ids) == expected_rows
        finally:
            await transaction.rollback()
            await conn.close()

    asyncio.run(check())


def test_profiles_receipts_notifications_and_alerts_are_role_scoped() -> None:
    async def check() -> None:
        conn = await connect()
        transaction = conn.transaction()
        await transaction.start()
        try:
            data = await seed_matrix(conn)
            expected_profiles = {
                REPORTER_ID: {REPORTER_ID},
                OTHER_REPORTER_ID: {OTHER_REPORTER_ID},
                REVIEWER_ID: set(PROFILE_IDS),
                RESPONSIBLE_ID: {RESPONSIBLE_ID},
                CREW_ID: {CREW_ID},
                ADMIN_ID: set(PROFILE_IDS),
            }
            expected_receipts = {
                REPORTER_ID: {data.own_receipt},
                OTHER_REPORTER_ID: {data.other_receipt},
                REVIEWER_ID: {data.own_receipt, data.other_receipt},
                RESPONSIBLE_ID: set(),
                CREW_ID: set(),
                ADMIN_ID: {data.own_receipt, data.other_receipt},
            }
            expected_notifications = {
                REPORTER_ID: {data.own_notification},
                OTHER_REPORTER_ID: {data.other_notification},
                REVIEWER_ID: set(),
                RESPONSIBLE_ID: set(),
                CREW_ID: set(),
                ADMIN_ID: set(),
            }
            expected_alerts = {
                REPORTER_ID: {data.own_alert},
                OTHER_REPORTER_ID: {data.other_alert},
                REVIEWER_ID: {data.own_alert, data.other_alert},
                RESPONSIBLE_ID: set(),
                CREW_ID: set(),
                ADMIN_ID: {data.own_alert, data.other_alert},
            }

            for profile_id in PROFILE_IDS:
                await assume_user(conn, profile_id)
                profile_rows = await conn.fetch(
                    "select id from public.profiles where id = any($1::uuid[])",
                    list(PROFILE_IDS),
                )
                assert {row["id"] for row in profile_rows} == expected_profiles[profile_id]
                assert await fetch_ids(
                    conn,
                    "closure_receipts",
                    (data.own_receipt, data.other_receipt),
                ) == expected_receipts[profile_id]
                assert await fetch_ids(
                    conn,
                    "notifications",
                    (data.own_notification, data.other_notification),
                ) == expected_notifications[profile_id]
                assert await fetch_ids(
                    conn, "alerts", (data.own_alert, data.other_alert)
                ) == expected_alerts[profile_id]
        finally:
            await transaction.rollback()
            await conn.close()

    asyncio.run(check())


def test_documents_and_only_published_lessons_are_visible_to_crew() -> None:
    async def check() -> None:
        conn = await connect()
        transaction = conn.transaction()
        await transaction.start()
        try:
            data = await seed_matrix(conn)
            for profile_id in PROFILE_IDS:
                await assume_user(conn, profile_id)
                assert await fetch_ids(conn, "documents", (data.document,)) == {
                    data.document
                }
                assert await fetch_ids(conn, "document_chunks", (data.chunk,)) == {
                    data.chunk
                }

                briefing_ids = await fetch_ids(
                    conn,
                    "briefings",
                    (data.draft_briefing, data.published_briefing),
                )
                question_ids = await fetch_ids(
                    conn,
                    "quiz_questions",
                    (data.draft_question, data.published_question),
                )
                if profile_id in {REVIEWER_ID, ADMIN_ID}:
                    assert briefing_ids == {
                        data.draft_briefing,
                        data.published_briefing,
                    }
                    assert question_ids == {
                        data.draft_question,
                        data.published_question,
                    }
                else:
                    assert briefing_ids == {data.published_briefing}
                    assert question_ids == {data.published_question}

            response_expectations = {
                REPORTER_ID: {data.reporter_response},
                OTHER_REPORTER_ID: set(),
                REVIEWER_ID: {data.crew_response, data.reporter_response},
                RESPONSIBLE_ID: set(),
                CREW_ID: {data.crew_response},
                ADMIN_ID: {data.crew_response, data.reporter_response},
            }
            for profile_id, expected in response_expectations.items():
                await assume_user(conn, profile_id)
                assert await fetch_ids(
                    conn,
                    "quiz_responses",
                    (data.crew_response, data.reporter_response),
                ) == expected
        finally:
            await transaction.rollback()
            await conn.close()

    asyncio.run(check())


def test_confidential_report_identity_is_masked_until_reviewer_access() -> None:
    async def check() -> None:
        conn = await connect()
        transaction = conn.transaction()
        await transaction.start()
        try:
            data = await seed_matrix(conn)

            await assume_user(conn, RESPONSIBLE_ID)
            responsible_row = await conn.fetchrow(
                "select reporter_id from public.reports_visible where id = $1",
                data.own_report,
            )
            assert responsible_row is not None
            assert responsible_row["reporter_id"] is None

            await assume_user(conn, REPORTER_ID)
            reporter_id = await conn.fetchval(
                "select reporter_id from public.reports_visible where id = $1",
                data.own_report,
            )
            assert reporter_id == REPORTER_ID

            await assume_user(conn, REVIEWER_ID)
            reviewer_id = await conn.fetchval(
                "select reporter_id from public.reports_visible where id = $1",
                data.own_report,
            )
            assert reviewer_id == REPORTER_ID
            await expect_denied(
                conn,
                "select reporter_id from public.reports where id = $1",
                data.own_report,
            )
        finally:
            await transaction.rollback()
            await conn.close()

    asyncio.run(check())


def test_forbidden_writes_fail_and_narrow_writes_stay_narrow() -> None:
    async def check() -> None:
        conn = await connect()
        transaction = conn.transaction()
        await transaction.start()
        try:
            data = await seed_matrix(conn)

            await assume_user(conn, REPORTER_ID)
            await expect_denied(
                conn,
                """
                insert into public.documents (title, doc_ref, revision)
                values ('Denied', $1, '1')
                """,
                f"DENIED-{uuid4()}",
            )
            await expect_denied(
                conn,
                """
                insert into public.document_chunks (
                  document_id, section, page, content, chunk_index
                ) values ($1, 'denied', 1, 'Denied chunk', 99)
                """,
                data.document,
            )
            await expect_denied(
                conn,
                """
                insert into public.alerts (report_id, raised_by, location_text)
                values ($1, $2, 'Spoofed')
                """,
                data.other_report,
                REPORTER_ID,
            )
            await expect_denied(
                conn,
                "update public.profiles set role = 'admin' where id = $1",
                REPORTER_ID,
            )
            assert await conn.execute(
                "update public.profiles set preferred_lang = 'zh-CN' where id = $1",
                REPORTER_ID,
            ) == "UPDATE 1"
            assert await conn.execute(
                "update public.notifications set read_at = now() where id = $1",
                data.own_notification,
            ) == "UPDATE 1"
            await expect_denied(
                conn,
                "update public.notifications set payload = '{}'::jsonb where id = $1",
                data.own_notification,
            )

            await assume_user(conn, OTHER_REPORTER_ID)
            assert await conn.execute(
                "update public.notifications set read_at = now() where id = $1",
                data.own_notification,
            ) == "UPDATE 0"
            assert await conn.execute(
                "update public.alerts set acknowledged_at = now() where id = $1",
                data.other_alert,
            ) == "UPDATE 0"

            await assume_user(conn, CREW_ID)
            await expect_denied(
                conn,
                """
                insert into public.briefings (report_id, version, body, status)
                values (
                  $1, 99, '{"en":"Denied","zh-CN":"拒绝"}'::jsonb, 'draft'
                )
                """,
                data.own_report,
            )
            await expect_denied(
                conn,
                """
                insert into public.quiz_responses (
                  question_id, respondent_id, selected_option, is_correct
                ) values ($1, $2, 0, true)
                """,
                data.published_question,
                CREW_ID,
            )
            await expect_denied(
                conn,
                """
                insert into public.quiz_questions (
                  briefing_id, position, question, explanation, options,
                  correct_option
                ) values (
                  $1, 99, '{"en":"Denied?","zh-CN":"拒绝？"}'::jsonb,
                  '{"en":"Denied","zh-CN":"拒绝"}'::jsonb,
                  '[{"en":"No","zh-CN":"否"}]'::jsonb, 0
                )
                """,
                data.published_briefing,
            )

            await assume_user(conn, REVIEWER_ID)
            inserted_document = await conn.fetchval(
                """
                insert into public.documents (title, doc_ref, revision, uploaded_by)
                values ('Allowed', $1, '1', $2) returning id
                """,
                f"ALLOWED-{uuid4()}",
                REVIEWER_ID,
            )
            assert inserted_document is not None
            assert await conn.execute(
                """
                update public.document_chunks
                set content = 'Reviewer-approved content'
                where id = $1
                """,
                data.chunk,
            ) == "UPDATE 1"
            assert await conn.execute(
                """
                update public.briefings
                set target_activity = 'Reviewer edit'
                where id = $1
                """,
                data.draft_briefing,
            ) == "UPDATE 1"
            assert await conn.execute(
                """
                update public.quiz_questions
                set explanation = '{"en":"Edited","zh-CN":"已编辑"}'::jsonb
                where id = $1
                """,
                data.draft_question,
            ) == "UPDATE 1"
            assert await conn.execute(
                """
                update public.alerts
                set acknowledged_by = $1, acknowledged_at = now()
                where id = $2
                """,
                REVIEWER_ID,
                data.own_alert,
            ) == "UPDATE 1"
            await expect_denied(
                conn,
                "update public.reports set status = 'submitted' where id = $1",
                data.own_report,
            )

            for table in (
                "report_media",
                "transcripts",
                "clarifications",
                "ai_drafts",
                "review_decisions",
                "report_assignments",
                "corrective_actions",
                "verifications",
                "audit_log",
                "closure_receipts",
            ):
                await expect_denied(conn, f"delete from public.{table}")

            await assume_anon(conn)
            await expect_denied(conn, "select * from public.documents")
            await expect_denied(conn, "select * from public.document_chunks")
            await expect_denied(conn, "select * from public.notifications")
        finally:
            await transaction.rollback()
            await conn.close()

    asyncio.run(check())


def test_storage_policies_use_guarded_predicates() -> None:
    async def check() -> None:
        conn = await connect()
        try:
            storage_exists = await conn.fetchval(
                "select to_regclass('storage.objects') is not null"
            )
            if not storage_exists:
                return
            policies = await conn.fetch(
                """
                select policyname, coalesce(qual, '') || coalesce(with_check, '') as expression
                from pg_policies
                where schemaname = 'storage'
                  and (
                    policyname like 'report_media_%'
                    or policyname like 'report_audio_%'
                  )
                """
            )
            assert len(policies) == 12
            expressions = " ".join(row["expression"] for row in policies)
            assert "safeloop_owns_report" in expressions
            assert "safeloop_has_active_assignment" in expressions
            assert "safeloop_can_manage_evidence_upload" in expressions
            assert "SELECT 1" not in expressions
        finally:
            await conn.close()

    asyncio.run(check())
