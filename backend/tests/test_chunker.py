"""Prove bilingual extraction keeps citation coordinates and structural boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.rag.chunker import (
    DOCX_MIME_TYPE,
    PDF_MIME_TYPE,
    ChunkingError,
    chunk_document,
    estimate_tokens,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_pdf_chunks_preserve_section_and_page() -> None:
    chunks = chunk_document(
        (FIXTURES / "english-procedure.pdf").read_bytes(),
        PDF_MIME_TYPE,
        max_tokens=40,
        overlap_tokens=8,
    )

    assert [(chunk.section, chunk.page) for chunk in chunks] == [
        ("1 Scope", 1),
        ("1.1 Guardrails", 1),
        ("2 Permit to work", 2),
        ("2.1 Stop work", 2),
    ]
    assert "Guardrail | Supervisor | Daily" in chunks[1].content


def test_simplified_chinese_docx_needs_no_word_spaces() -> None:
    chunks = chunk_document(
        (FIXTURES / "zh-CN-procedure.docx").read_bytes(),
        DOCX_MIME_TYPE,
        max_tokens=40,
        overlap_tokens=8,
    )

    assert any("六楼及以上的高处作业" in chunk.content for chunk in chunks)
    assert any(chunk.section == "1.1 检查" and chunk.page == 1 for chunk in chunks)
    assert estimate_tokens("六楼边缘没有护栏") == 8


def test_numbered_clause_is_not_split_even_when_over_target() -> None:
    chunks = chunk_document(
        (FIXTURES / "zh-CN-procedure.docx").read_bytes(),
        DOCX_MIME_TYPE,
        max_tokens=5,
        overlap_tokens=1,
    )

    scope = next(chunk for chunk in chunks if chunk.section == "1 范围")
    assert scope.content.startswith("1 范围\n")
    assert "开始工作前必须安装护栏" in scope.content
    assert estimate_tokens(scope.content) > 5


def test_unsupported_source_fails_with_machine_code() -> None:
    with pytest.raises(ChunkingError) as error:
        chunk_document(b"plain text", "text/plain")
    assert error.value.code == "document_type_not_allowed"
