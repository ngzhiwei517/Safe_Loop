"""Extract corpus sources without losing the boundaries a citation must preserve."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from io import BytesIO
import re
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader
from pypdf.errors import PdfReadError

PDF_MIME_TYPE = "application/pdf"
DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_NUMBERED_CLAUSE = re.compile(r"^\s*(\d+(?:\.\d+)*[.)]?)\s+\S")
_TOKEN = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*|[\u3400-\u9fff]|[^\s]")
_SENTENCE = re.compile(r".+?(?:[.!?。！？；;]+(?=\s|$)|$)", re.DOTALL)
_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = f"{{{_WORD_NS}}}"


class ChunkingError(ValueError):
    """Reject a source using a stable code suitable for the API boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class TextUnit:
    """Keep one structural unit indivisible while chunks are packed."""

    section: str | None
    page: int | None
    content: str


@dataclass(frozen=True)
class DocumentChunk:
    """Carry the citation coordinates alongside extracted content."""

    section: str | None
    page: int | None
    content: str


def estimate_tokens(text: str) -> int:
    """Count Latin terms and CJK characters without assuming words need spaces."""
    return len(_TOKEN.findall(text))


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _sentences(text: str) -> list[str]:
    cleaned = _clean_text(text)
    return [match.group(0).strip() for match in _SENTENCE.finditer(cleaned) if match.group(0).strip()]


def _is_heading(text: str) -> bool:
    if _NUMBERED_CLAUSE.match(text):
        return True
    letters = [character for character in text if character.isalpha()]
    return bool(letters) and len(text) <= 120 and all(
        not character.isalpha() or character.isupper() for character in text
    )


def _units_from_lines(
    lines: Iterable[tuple[str, bool, bool]],
    *,
    page: int | None,
) -> list[TextUnit]:
    units: list[TextUnit] = []
    section: str | None = None
    clause_lines: list[str] = []
    clause_section: str | None = None

    def flush_clause() -> None:
        if clause_lines:
            units.append(TextUnit(clause_section, page, "\n".join(clause_lines)))
            clause_lines.clear()

    for raw_text, explicit_heading, table_row in lines:
        text = _clean_text(raw_text)
        if not text:
            continue
        numbered = _NUMBERED_CLAUSE.match(text) is not None
        heading = explicit_heading or _is_heading(text)
        if numbered:
            flush_clause()
            section = text
            clause_section = section
            clause_lines.append(text)
            continue
        if clause_lines and not heading:
            clause_lines.append(text)
            continue
        flush_clause()
        if heading:
            section = text
            units.append(TextUnit(section, page, text))
        elif table_row:
            units.append(TextUnit(section, page, text))
        else:
            units.extend(TextUnit(section, page, sentence) for sentence in _sentences(text))
    flush_clause()
    return units


def _pdf_units(content: bytes) -> list[TextUnit]:
    try:
        reader = PdfReader(BytesIO(content))
    except (PdfReadError, ValueError, OSError) as error:
        raise ChunkingError("document_parse_failed", "PDF source could not be parsed") from error
    units: list[TextUnit] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except (KeyError, ValueError) as error:
            raise ChunkingError("document_parse_failed", "PDF page text could not be extracted") from error
        lines = [
            (line, False, "|" in line or "\t" in line)
            for line in text.splitlines()
            if line.strip()
        ]
        units.extend(_units_from_lines(lines, page=page_number))
    return units


def _paragraph_text(element: ElementTree.Element) -> str:
    return "".join(node.text or "" for node in element.iter(f"{_W}t"))


def _docx_units(content: bytes) -> list[TextUnit]:
    try:
        with ZipFile(BytesIO(content)) as archive:
            xml = archive.read("word/document.xml")
    except (BadZipFile, KeyError, OSError) as error:
        raise ChunkingError("document_parse_failed", "DOCX source could not be opened") from error
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as error:
        raise ChunkingError("document_parse_failed", "DOCX XML could not be parsed") from error

    body = root.find(f"{_W}body")
    if body is None:
        raise ChunkingError("document_parse_failed", "DOCX document body is missing")
    page = 1
    lines: list[tuple[str, bool, bool]] = []
    units: list[TextUnit] = []
    for child in body:
        if child.tag == f"{_W}p":
            text = _paragraph_text(child)
            style_node = child.find(f"{_W}pPr/{_W}pStyle")
            style = style_node.get(f"{_W}val", "") if style_node is not None else ""
            is_heading = style.lower().startswith("heading")
            if text.strip():
                lines.append((text, is_heading, False))
            has_page_break = child.find(f".//{_W}lastRenderedPageBreak") is not None or any(
                node.get(f"{_W}type") == "page" for node in child.iter(f"{_W}br")
            )
            if has_page_break:
                units.extend(_units_from_lines(lines, page=page))
                lines = []
                page += 1
        elif child.tag == f"{_W}tbl":
            for row in child.findall(f"{_W}tr"):
                cells = [_clean_text(_paragraph_text(cell)) for cell in row.findall(f"{_W}tc")]
                lines.append((" | ".join(cell for cell in cells if cell), False, True))
    units.extend(_units_from_lines(lines, page=page))
    return units


def extract_units(content: bytes, mime_type: str) -> list[TextUnit]:
    """Extract a supported source and fail rather than ingest an empty corpus entry."""
    if mime_type == PDF_MIME_TYPE:
        units = _pdf_units(content)
    elif mime_type == DOCX_MIME_TYPE:
        units = _docx_units(content)
    else:
        raise ChunkingError("document_type_not_allowed", "document type is not supported")
    if not units or not any(unit.content.strip() for unit in units):
        raise ChunkingError("document_text_empty", "document contains no extractable text")
    return units


def _pack_group(
    units: list[TextUnit],
    *,
    max_tokens: int,
    overlap_tokens: int,
) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    current: list[TextUnit] = []

    def emit() -> None:
        if current:
            first = current[0]
            chunks.append(
                DocumentChunk(first.section, first.page, "\n".join(unit.content for unit in current))
            )

    for unit in units:
        proposed = current + [unit]
        if current and estimate_tokens("\n".join(item.content for item in proposed)) > max_tokens:
            emit()
            overlap: list[TextUnit] = []
            overlap_size = 0
            for prior in reversed(current):
                size = estimate_tokens(prior.content)
                if overlap and overlap_size + size > overlap_tokens:
                    break
                if size > overlap_tokens:
                    break
                overlap.insert(0, prior)
                overlap_size += size
            current = overlap
            if current and estimate_tokens(
                "\n".join(item.content for item in current + [unit])
            ) > max_tokens:
                current = []
        current.append(unit)
    emit()
    return chunks


def chunk_document(
    content: bytes,
    mime_type: str,
    *,
    max_tokens: int = 800,
    overlap_tokens: int = 120,
) -> list[DocumentChunk]:
    """Pack structural units while keeping page and section citation coordinates exact."""
    if max_tokens <= 0 or overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError("chunk token limits are invalid")
    units = extract_units(content, mime_type)
    chunks: list[DocumentChunk] = []
    group: list[TextUnit] = []
    coordinates: tuple[str | None, int | None] | None = None
    for unit in units:
        unit_coordinates = (unit.section, unit.page)
        if coordinates is not None and unit_coordinates != coordinates:
            chunks.extend(
                _pack_group(group, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
            )
            group = []
        coordinates = unit_coordinates
        group.append(unit)
    if group:
        chunks.extend(_pack_group(group, max_tokens=max_tokens, overlap_tokens=overlap_tokens))
    return chunks
