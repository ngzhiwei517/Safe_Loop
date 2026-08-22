"""Verify deterministic structured AI behavior without allowing a network escape hatch."""

from __future__ import annotations

import asyncio
from math import isclose
from typing import Literal

from pydantic import BaseModel, Field
import pytest

from app.ai.prompts import PromptError, load_prompt, render_prompt
from app.ai.provider import (
    EMBEDDING_DIMENSIONS,
    ProviderConfigurationError,
    StubProvider,
    get_provider,
)
from app.config import get_settings


class FixtureSchema(BaseModel):
    observed_facts: list[str] = Field(min_length=1, max_length=2)
    confidence: float = Field(ge=0.0, le=1.0)
    needs_escalation: bool
    locale: Literal["en", "zh-CN"]


def complete(
    provider: StubProvider,
    *,
    report: str = "Loose edge protection",
):
    return asyncio.run(
        provider.complete(
            "provider_fixture",
            {"report": report, "locale": "en"},
            schema=FixtureSchema,
        )
    )


def test_identical_completion_input_is_fully_deterministic() -> None:
    provider = StubProvider()
    first = complete(provider)
    second = complete(provider)

    assert first == second
    assert FixtureSchema.model_validate(first.data)
    assert first.provider == "stub"
    assert first.provider_ref.startswith("stub-")


def test_changed_input_changes_the_deterministic_run() -> None:
    provider = StubProvider()
    first = complete(provider)
    changed = complete(provider, report="Blocked fire exit")

    assert first.provider_ref != changed.provider_ref
    assert first.raw != changed.raw


def test_embeddings_are_deterministic_and_match_pgvector_dimensions() -> None:
    provider = StubProvider()
    first = asyncio.run(provider.embed(["same text", "different text"]))
    second = asyncio.run(provider.embed(["same text", "different text"]))

    assert first == second
    assert len(first) == 2
    assert all(len(vector) == EMBEDDING_DIMENSIONS for vector in first)
    assert first[0] != first[1]
    assert all(-1.0 <= value <= 1.0 for vector in first for value in vector)
    assert all(
        isclose(sum(value * value for value in vector), 1.0, rel_tol=1e-6)
        for vector in first
    )


def test_mandarin_lexical_overlap_is_reflected_in_stub_similarity() -> None:
    provider = StubProvider()
    query, relevant, noise = asyncio.run(
        provider.embed(
            [
                "开始工作前必须安装护栏",
                "本程序适用于高处作业。开始工作前必须安装护栏。",
                "食堂菜单和办公室文具清单",
            ]
        )
    )

    def cosine(left: list[float], right: list[float]) -> float:
        return sum(left_value * right_value for left_value, right_value in zip(left, right))

    assert cosine(query, relevant) >= 0.35
    assert cosine(query, relevant) > cosine(query, noise)


def test_prompt_loader_reads_markdown_and_renders_variables() -> None:
    assert "{{report}}" in load_prompt("provider_fixture")
    rendered = render_prompt(
        "provider_fixture",
        {"report": "六楼边缘没有护栏", "locale": "zh-CN"},
    )
    assert "六楼边缘没有护栏" in rendered
    assert "zh-CN" in rendered
    assert "{{" not in rendered


@pytest.mark.parametrize("name", ["../provider_fixture", "provider_fixture.md", "UPPER"])
def test_prompt_loader_rejects_unsafe_names(name: str) -> None:
    with pytest.raises(PromptError):
        load_prompt(name)


def test_prompt_loader_rejects_missing_variables() -> None:
    with pytest.raises(PromptError):
        render_prompt("provider_fixture", {"report": "Hazard"})


def test_factory_reads_the_stub_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "stub")
    get_settings.cache_clear()
    try:
        assert isinstance(get_provider(), StubProvider)
    finally:
        get_settings.cache_clear()


def test_factory_rejects_an_unimplemented_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "real")
    get_settings.cache_clear()
    try:
        with pytest.raises(ProviderConfigurationError):
            get_provider()
    finally:
        get_settings.cache_clear()


def test_stub_refuses_an_implicit_test_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    with pytest.raises(ProviderConfigurationError):
        StubProvider()


def test_external_socket_calls_are_blocked() -> None:
    import socket

    with pytest.raises(AssertionError, match="external network access"):
        socket.create_connection(("203.0.113.1", 443), timeout=0.01)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        with pytest.raises(AssertionError, match="external network access"):
            connection.connect(("203.0.113.1", 443))
