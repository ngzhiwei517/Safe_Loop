"""Map shared request-limit failures to the API's machine-coded contract."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.services.rate_limit_service import RateLimitExceeded, consume_rate_limit


async def enforce_rate_limit(
    *,
    scope: str,
    subject: str,
    limit: int,
    error_code: str,
) -> None:
    """Consume one request slot or raise a localisable 429 response."""
    try:
        await consume_rate_limit(scope=scope, subject=subject, limit=limit)
    except RateLimitExceeded as error:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            {
                "code": error_code,
                "message": "request rate limit exceeded",
            },
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from error
