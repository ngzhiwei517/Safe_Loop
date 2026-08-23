"""Expose the reviewer-owned approved-document corpus as machine-coded HTTP contracts."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Annotated, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.encoders import jsonable_encoder

from app.api.deps import current_actor
from app.api.rate_limits import enforce_rate_limit
from app.config import get_settings
from app.services.document_service import (
    DocumentError,
    approve_document,
    ingest_document,
    list_documents,
    retire_document,
)
from app.services.report_service import Actor

router = APIRouter(prefix="/documents", tags=["documents"])


def document_error(error: DocumentError) -> HTTPException:
    """Map corpus codes without making developer prose part of the UI contract."""
    code_status = {
        "document_actor_forbidden": status.HTTP_403_FORBIDDEN,
        "document_not_found": status.HTTP_404_NOT_FOUND,
        "document_too_large": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        "document_storage_not_configured": status.HTTP_503_SERVICE_UNAVAILABLE,
        "document_storage_failed": status.HTTP_502_BAD_GATEWAY,
    }
    return HTTPException(
        code_status.get(error.code, status.HTTP_422_UNPROCESSABLE_ENTITY),
        {"code": error.code, "message": error.message},
    )


@router.get("")
async def get_documents(actor: Actor = Depends(current_actor)) -> list[dict[str, object]]:
    """List exact revisions with approval and citation evidence."""
    try:
        documents = await list_documents(actor)
    except DocumentError as error:
        raise document_error(error) from error
    return cast(list[dict[str, object]], jsonable_encoder([dict(row) for row in documents]))


@router.post("", status_code=status.HTTP_201_CREATED)
async def post_document(
    title: Annotated[str, Form(min_length=1, max_length=500)],
    doc_ref: Annotated[str, Form(min_length=1, max_length=200)],
    revision: Annotated[str, Form(min_length=1, max_length=100)],
    file: Annotated[UploadFile, File()],
    effective_from: Annotated[date | None, Form()] = None,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Receive one source and replace only its exact revision's chunks."""
    if actor.profile_id is not None:
        await enforce_rate_limit(
            scope="document_upload",
            subject=str(actor.profile_id),
            limit=get_settings().document_upload_rate_limit_per_minute,
            error_code="document_rate_limited",
        )
    content = await file.read()
    try:
        document = await ingest_document(
            actor,
            title=title,
            doc_ref=doc_ref,
            revision=revision,
            effective_from=(
                datetime.combine(
                    effective_from,
                    time.min,
                    ZoneInfo(get_settings().site_timezone),
                )
                if effective_from is not None
                else None
            ),
            filename=file.filename or "",
            claimed_mime_type=file.content_type or "",
            content=content,
        )
    except DocumentError as error:
        raise document_error(error) from error
    return cast(dict[str, object], jsonable_encoder(dict(document)))


@router.post("/{document_id}/approve")
async def post_document_approve(
    document_id: UUID,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Approve one document row, never its reference family."""
    try:
        document = await approve_document(document_id, actor)
    except DocumentError as error:
        raise document_error(error) from error
    return cast(dict[str, object], jsonable_encoder(dict(document)))


@router.post("/{document_id}/retire")
async def post_document_retire(
    document_id: UUID,
    actor: Actor = Depends(current_actor),
) -> dict[str, object]:
    """Retire one document row, never its reference family."""
    try:
        document = await retire_document(document_id, actor)
    except DocumentError as error:
        raise document_error(error) from error
    return cast(dict[str, object], jsonable_encoder(dict(document)))
