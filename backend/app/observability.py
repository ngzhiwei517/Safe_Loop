"""Correlate requests, failures, and bounded latency samples without external I/O."""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import logging
from math import ceil
import re
import sys
from threading import Lock
from time import perf_counter
from typing import Final, TypeAlias, cast
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)

REQUEST_ID_HEADER: Final = "X-Request-ID"
ERROR_ID_HEADER: Final = "X-Error-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_request_id: ContextVar[str | None] = ContextVar("safeloop_request_id", default=None)

_LOG_RECORD_FIELDS: Final = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
    }
)


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str) or type(value) in {int, float, bool}:
        return cast(str | int | float | bool | None, value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(item) for item in value]
    return str(value)


def current_request_id() -> str | None:
    """Return the correlation identifier inherited by the current async task."""
    return _request_id.get()


def _safe_request_id(value: str | None) -> str:
    if value is not None and _REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return str(uuid4())


@contextmanager
def bind_request_id(value: str | None = None) -> Iterator[str]:
    """Bind an explicit HTTP identifier across graph and provider await points."""
    request_id = _safe_request_id(value or current_request_id())
    token = _request_id.set(request_id)
    try:
        yield request_id
    finally:
        _request_id.reset(token)


class JsonFormatter(logging.Formatter):
    """Emit one parseable object per record while retaining typed extra fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, JsonValue] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or current_request_id()
        if isinstance(request_id, str):
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key not in _LOG_RECORD_FIELDS and key not in {"request_id", "message"}:
                payload[key] = _json_value(value)
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_json_logging(level_name: str) -> None:
    """Make application and library records share the same production log shape."""
    level = getattr(logging, level_name.strip().upper(), logging.INFO)
    root = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level if isinstance(level, int) else logging.INFO)


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    **fields: object,
) -> None:
    """Attach correlation data without relying on prose parsing downstream."""
    extra = {**fields, "request_id": current_request_id()}
    logger.log(level, event, extra=extra)


@dataclass
class _EndpointStats:
    count: int = 0
    error_count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    samples: deque[float] = field(default_factory=deque)


class LatencyRegistry:
    """Keep bounded process-local aggregates while every sample also reaches logs."""

    def __init__(self, *, max_samples: int = 1000) -> None:
        self._max_samples = max_samples
        self._stats: dict[str, _EndpointStats] = {}
        self._lock = Lock()

    def record(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        key = f"{method.upper()} {endpoint}"
        with self._lock:
            stats = self._stats.setdefault(key, _EndpointStats())
            if stats.samples.maxlen != self._max_samples:
                stats.samples = deque(stats.samples, maxlen=self._max_samples)
            stats.count += 1
            stats.error_count += int(status_code >= 500)
            stats.total_ms += duration_ms
            stats.max_ms = max(stats.max_ms, duration_ms)
            stats.samples.append(duration_ms)

    def snapshot(self) -> dict[str, dict[str, int | float]]:
        with self._lock:
            result: dict[str, dict[str, int | float]] = {}
            for endpoint, stats in sorted(self._stats.items()):
                ordered = sorted(stats.samples)
                p95_index = max(0, ceil(len(ordered) * 0.95) - 1)
                result[endpoint] = {
                    "count": stats.count,
                    "error_count": stats.error_count,
                    "average_ms": round(stats.total_ms / stats.count, 3),
                    "p95_ms": round(ordered[p95_index], 3),
                    "max_ms": round(stats.max_ms, 3),
                }
            return result

    def reset(self) -> None:
        with self._lock:
            self._stats.clear()


class ErrorRegistry:
    """Index recent opaque error IDs while stack traces remain in structured logs."""

    def __init__(self, *, max_recent: int = 100) -> None:
        self._recent: deque[dict[str, str]] = deque(maxlen=max_recent)
        self._by_type: Counter[str] = Counter()
        self._lock = Lock()

    def track(self, event: str, error: BaseException) -> str:
        error_id = str(uuid4())
        item = {
            "error_id": error_id,
            "request_id": current_request_id() or "",
            "event": event,
            "error_type": type(error).__name__,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        with self._lock:
            self._recent.append(item)
            self._by_type[type(error).__name__] += 1
        return error_id

    def snapshot(self) -> dict[str, JsonValue]:
        with self._lock:
            return {
                "total": sum(self._by_type.values()),
                "by_type": dict(sorted(self._by_type.items())),
                "recent": _json_value(tuple(self._recent)),
            }

    def reset(self) -> None:
        with self._lock:
            self._recent.clear()
            self._by_type.clear()


LATENCY_METRICS = LatencyRegistry()
ERRORS = ErrorRegistry()


def track_exception(
    logger: logging.Logger,
    event: str,
    error: BaseException,
    **fields: object,
) -> str:
    """Give one failure a stable handle and emit its complete traceback once."""
    error_id = ERRORS.track(event, error)
    extra = {
        **fields,
        "error_id": error_id,
        "error_type": type(error).__name__,
        "request_id": current_request_id(),
    }
    logger.error(
        event,
        extra=extra,
        exc_info=(type(error), error, error.__traceback__),
    )
    return error_id


def operational_snapshot() -> dict[str, JsonValue]:
    """Return aggregate operations data without request bodies or credentials."""
    return {
        "latency": cast(dict[str, JsonValue], LATENCY_METRICS.snapshot()),
        "errors": ERRORS.snapshot(),
    }


def _endpoint_name(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else request.url.path


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    """Emit one completion event and one tracked event for unhandled failures."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        slow_request_ms: int,
        registry: LatencyRegistry = LATENCY_METRICS,
    ) -> None:
        super().__init__(app)
        self._slow_request_ms = slow_request_ms
        self._registry = registry
        self._logger = logging.getLogger("app.http")

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        supplied_id = request.headers.get(REQUEST_ID_HEADER)
        with bind_request_id(supplied_id) as request_id:
            started = perf_counter()
            error_id: str | None = None
            try:
                response = await call_next(request)
            except Exception as error:
                error_id = track_exception(
                    self._logger,
                    "request_failed",
                    error,
                    method=request.method,
                    endpoint=_endpoint_name(request),
                )
                response = JSONResponse(
                    status_code=500,
                    content={
                        "detail": {
                            "code": "internal_error",
                            "message": "unhandled server error",
                        }
                    },
                )
            duration_ms = round((perf_counter() - started) * 1000, 3)
            endpoint = _endpoint_name(request)
            self._registry.record(
                request.method,
                endpoint,
                response.status_code,
                duration_ms,
            )
            slow = duration_ms >= self._slow_request_ms
            level = (
                logging.ERROR
                if response.status_code >= 500
                else logging.WARNING
                if slow
                else logging.INFO
            )
            log_event(
                self._logger,
                level,
                "request_completed",
                method=request.method,
                endpoint=endpoint,
                status_code=response.status_code,
                latency_ms=duration_ms,
                slow=slow,
                error_id=error_id,
            )
            response.headers[REQUEST_ID_HEADER] = request_id
            if error_id is not None:
                response.headers[ERROR_ID_HEADER] = error_id
            return response
