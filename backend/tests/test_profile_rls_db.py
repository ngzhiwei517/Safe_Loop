"""Prove profile RLS exposes only the signed-in user's safe fields."""

from __future__ import annotations

import asyncio
import os
from uuid import UUID

import asyncpg
import pytest

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")
REPORTER_ID = UUID("00000000-0000-0000-0000-000000000001")


async def connect() -> asyncpg.Connection[asyncpg.Record]:
    assert DATABASE_URL is not None
    return await asyncpg.connect(DATABASE_URL)


def test_profile_grants_and_policies_are_least_privilege() -> None:
    async def check() -> None:
        conn = await connect()
        try:
            grants = await conn.fetch(
                """
                select grantee, privilege_type
                from information_schema.role_table_grants
                where table_schema = 'public'
                  and table_name = 'profiles'
                  and grantee in ('anon', 'authenticated')
                """
            )
            assert {(row["grantee"], row["privilege_type"]) for row in grants} == {
                ("authenticated", "SELECT")
            }

            column_grants = await conn.fetch(
                """
                select column_name, privilege_type
                from information_schema.role_column_grants
                where table_schema = 'public'
                  and table_name = 'profiles'
                  and grantee = 'authenticated'
                """
            )
            explicit_update_columns = {
                row["column_name"]
                for row in column_grants
                if row["privilege_type"] == "UPDATE"
            }
            assert explicit_update_columns == {"preferred_lang"}

            policies = await conn.fetch(
                """
                select policyname, cmd
                from pg_policies
                where schemaname = 'public' and tablename = 'profiles'
                """
            )
            assert {(row["policyname"], row["cmd"]) for row in policies} == {
                ("profiles_select_visible", "SELECT"),
                ("profiles_update_own_language", "UPDATE"),
            }
        finally:
            await conn.close()

    asyncio.run(check())


def test_authenticated_user_sees_self_and_updates_only_language() -> None:
    async def check() -> None:
        conn = await connect()
        transaction = conn.transaction()
        await transaction.start()
        try:
            await conn.execute(
                "select set_config('request.jwt.claim.sub', $1, true)",
                str(REPORTER_ID),
            )
            await conn.execute("set local role authenticated")

            rows = await conn.fetch("select id from public.profiles")
            assert [row["id"] for row in rows] == [REPORTER_ID]

            result = await conn.execute(
                "update public.profiles set preferred_lang = 'zh-CN' where id = $1",
                REPORTER_ID,
            )
            assert result == "UPDATE 1"

            savepoint = conn.transaction()
            await savepoint.start()
            try:
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    await conn.execute(
                        "update public.profiles set role = 'admin' where id = $1",
                        REPORTER_ID,
                    )
            finally:
                await savepoint.rollback()
        finally:
            await transaction.rollback()
            await conn.close()

    asyncio.run(check())
