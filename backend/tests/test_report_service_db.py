"""Integration tests proving the service and database guards together."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from uuid import UUID, uuid4

import asyncpg
import pytest

from app.db import close_pool, connection, init_pool
from app.domain.enums import ActorType, InputMode, ReportStatus, Role
from app.domain.transitions import TransitionError
from app.services.report_service import Actor, create_report, transition_report

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")
REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")
REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000003")
RESPONSIBLE_ID = UUID("00000000-0000-0000-0000-000000000004")
_test_loop: asyncio.AbstractEventLoop | None = None


@pytest.fixture(scope="module", autouse=True)
def database_pool() -> Iterator[None]:
    """Share one pool per module and close it after all integration cases."""
    global _test_loop
    assert DATABASE_URL is not None
    _test_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_test_loop)
    _test_loop.run_until_complete(init_pool(DATABASE_URL))
    yield
    _test_loop.run_until_complete(close_pool())
    _test_loop.close()
    _test_loop = None
    asyncio.set_event_loop(None)


def run(coroutine):  # type: ignore[no-untyped-def]
    """Keep the integration suite dependency-free beyond asyncpg and pytest."""
    assert _test_loop is not None
    return _test_loop.run_until_complete(coroutine)


async def cleanup(report_id: UUID) -> None:
    async with connection() as conn:
        await conn.execute("DELETE FROM reports WHERE id = $1", report_id)


async def make_report() -> UUID:
    return await create_report(REPORTER_ID, f"integration fixture {uuid4()}")


def test_create_report_writes_audit_and_human_ref() -> None:
    report_id = run(make_report())
    try:
        async def check() -> tuple[str, int]:
            async with connection() as conn:
                return await conn.fetchrow(
                    """
                    select human_ref, (select count(*) from audit_log where report_id = $1)
                    from reports where id = $1
                    """,
                    report_id,
                )

        human_ref, audit_count = run(check())
        assert human_ref.startswith("SL-")
        assert audit_count == 1
    finally:
        run(cleanup(report_id))


def test_file_report_contract_persists_fields_and_two_audits() -> None:
    report_id = run(create_report(
        REPORTER_ID,
        "Loose edge protection",
        lang_original="en",
        location_text="Level 6",
        activity="Material delivery",
        level_or_zone="East loading area",
        grid_ref="E6",
        is_confidential=True,
        input_mode=InputMode.TYPED,
    ))
    try:
        run(transition_report(
            report_id,
            ReportStatus.SUBMITTED,
            Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER),
        ))

        async def check() -> tuple[str, str, str, bool, int]:
            async with connection() as conn:
                return await conn.fetchrow(
                    """
                    select status::text, input_mode::text, grid_ref, is_confidential,
                           (select count(*) from audit_log where report_id = $1)
                    from reports where id = $1
                    """,
                    report_id,
                )

        assert run(check()) == ("submitted", "typed", "E6", True, 2)
    finally:
        run(cleanup(report_id))


def test_legal_transition_updates_status_and_adds_one_audit() -> None:
    report_id = run(make_report())
    try:
        run(transition_report(
            report_id,
            ReportStatus.SUBMITTED,
            Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER),
        ))
        async def check() -> tuple[str, int]:
            async with connection() as conn:
                return await conn.fetchrow(
                    "select (select status::text from reports where id = $1), count(*) from audit_log where report_id = $1",
                    report_id,
                )

        status_value, audit_count = run(check())
        assert status_value == "submitted"
        assert audit_count == 2
    finally:
        run(cleanup(report_id))


def test_illegal_transition_leaves_status_and_audit_untouched() -> None:
    report_id = run(make_report())
    try:
        with pytest.raises(TransitionError) as error:
            run(transition_report(report_id, ReportStatus.UNDER_REVIEW, Actor.system()))
        assert error.value.code == "illegal_transition"
        async def check() -> tuple[str, int]:
            async with connection() as conn:
                return await conn.fetchrow(
                    "select (select status::text from reports where id = $1), count(*) from audit_log where report_id = $1",
                    report_id,
                )

        status_value, audit_count = run(check())
        assert status_value == "draft"
        assert audit_count == 1
    finally:
        run(cleanup(report_id))


def test_concurrent_transitions_serialize() -> None:
    report_id = run(make_report())
    try:
        async def attempt():
            return await transition_report(
                report_id,
                ReportStatus.SUBMITTED,
                Actor(ActorType.HUMAN, REPORTER_ID, Role.REPORTER),
            )

        async def both():
            return await asyncio.gather(attempt(), attempt(), return_exceptions=True)

        results = run(both())
        assert sum(not isinstance(result, Exception) for result in results) == 1
        assert sum(isinstance(result, TransitionError) for result in results) == 1
    finally:
        run(cleanup(report_id))


def test_raw_sql_ai_closure_is_rejected() -> None:
    report_id = run(make_report())
    try:
        async def check() -> str:
            async with connection() as conn:
                await conn.execute("select set_config('safeloop.actor_type', 'human', true)")
                await conn.execute("update reports set status = 'action_submitted' where id = $1", report_id)
                await conn.execute("select set_config('safeloop.actor_type', 'ai', true)")
                with pytest.raises(asyncpg.InsufficientPrivilegeError) as error:
                    await conn.execute("update reports set status = 'verified_closed' where id = $1", report_id)
                assert error.value.sqlstate == "42501"
                return await conn.fetchval("select status::text from reports where id = $1", report_id)

        assert run(check()) == "action_submitted"
    finally:
        run(cleanup(report_id))


def test_raw_sql_ai_draft_update_is_rejected() -> None:
    report_id = run(make_report())
    try:
        async def check() -> None:
            async with connection() as conn:
                draft_id = await conn.fetchval(
                    """
                    insert into ai_drafts (report_id, version, provider, provider_ref, raw_json, observed_facts, assumptions, missing_information)
                    values ($1, 1, 'stub', 'fixture', '{}', '[]', '[]', '[]') returning id
                    """, report_id,
                )
                with pytest.raises(asyncpg.InsufficientPrivilegeError) as error:
                    await conn.execute("update ai_drafts set provider_ref = 'changed' where id = $1", draft_id)
                assert error.value.sqlstate == "42501"

        run(check())
    finally:
        run(cleanup(report_id))


def test_raw_sql_verification_update_is_rejected() -> None:
    report_id = run(make_report())
    try:
        async def check() -> None:
            async with connection() as conn:
                assignment_id = await conn.fetchval(
                    """
                    insert into report_assignments (report_id, assignee_id, case_role, due_at)
                    values ($1, $2, 'responsible', now()) returning id
                    """, report_id, RESPONSIBLE_ID,
                )
                action_id = await conn.fetchval(
                    """
                    insert into corrective_actions (report_id, assignment_id, action_text, due_at)
                    values ($1, $2, 'fixture action', now()) returning id
                    """, report_id, assignment_id,
                )
                verification_id = await conn.fetchval(
                    """
                    insert into verifications (report_id, corrective_action_id, reviewer_id, passed, notes)
                    values ($1, $2, $3, true, 'fixture') returning id
                    """, report_id, action_id, REVIEWER_ID,
                )
                with pytest.raises(asyncpg.InsufficientPrivilegeError) as error:
                    await conn.execute("update verifications set notes = 'changed' where id = $1", verification_id)
                assert error.value.sqlstate == "42501"

        run(check())
    finally:
        run(cleanup(report_id))


def test_postgres_report_status_enum_matches_domain() -> None:
    async def check() -> list[str]:
        async with connection() as conn:
            return await conn.fetch(
                """
                select enumlabel from pg_enum
                where enumtypid = 'report_status'::regtype order by enumsortorder
                """
            )

    labels = [row["enumlabel"] for row in run(check())]
    assert labels == [status.value for status in ReportStatus]
