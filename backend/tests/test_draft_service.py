"""Keep the service API append-only even before PostgreSQL guards run."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

import pytest

from app.services import draft_service
from app.services.draft_service import DraftPersistenceError, update_draft


def test_service_refuses_every_draft_update() -> None:
    with pytest.raises(DraftPersistenceError) as error:
        asyncio.run(
            update_draft(
                UUID("20000000-0000-0000-0000-000000000001"),
                {"confidence": 0.5},
            )
        )

    assert error.value.code == "draft_append_only"


def test_draft_service_contains_no_ai_drafts_update_statement() -> None:
    source = Path(draft_service.__file__).read_text(encoding="utf-8").casefold()

    assert "update ai_drafts" not in source
