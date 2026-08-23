"""Aggregate provider calls that belong to one restartable graph invocation."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator


@dataclass(frozen=True)
class AIUsageSnapshot:
    providers: tuple[str, ...]
    provider_refs: tuple[str, ...]
    operations: tuple[str, ...]
    provider_latency_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    call_count: int

    def as_log_fields(self, *, fallback_provider: str) -> dict[str, object]:
        """Return stable fields even when a provider failed before yielding usage."""
        provider = (
            self.providers[0]
            if len(self.providers) == 1
            else ",".join(self.providers)
            if self.providers
            else fallback_provider
        )
        return {
            "provider": provider,
            "provider_refs": list(self.provider_refs),
            "provider_operations": list(self.operations),
            "provider_latency_ms": self.provider_latency_ms,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": self.cost_usd,
            "provider_call_count": self.call_count,
        }


@dataclass
class AIUsageAccumulator:
    providers: set[str] = field(default_factory=set)
    provider_refs: list[str] = field(default_factory=list)
    operations: list[str] = field(default_factory=list)
    provider_latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    call_count: int = 0

    def snapshot(self) -> AIUsageSnapshot:
        return AIUsageSnapshot(
            providers=tuple(sorted(self.providers)),
            provider_refs=tuple(self.provider_refs),
            operations=tuple(self.operations),
            provider_latency_ms=self.provider_latency_ms,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            cost_usd=round(self.cost_usd, 8),
            call_count=self.call_count,
        )


_active_usage: ContextVar[AIUsageAccumulator | None] = ContextVar(
    "safeloop_ai_usage",
    default=None,
)


@contextmanager
def capture_ai_usage() -> Iterator[AIUsageAccumulator]:
    """Bind one mutable accumulator across sequential LangGraph node tasks."""
    accumulator = AIUsageAccumulator()
    token = _active_usage.set(accumulator)
    try:
        yield accumulator
    finally:
        _active_usage.reset(token)


def record_ai_usage(
    *,
    provider: str,
    provider_ref: str,
    operation: str,
    latency_ms: int,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
) -> None:
    """Ignore standalone calls and aggregate only calls inside a declared graph run."""
    accumulator = _active_usage.get()
    if accumulator is None:
        return
    accumulator.providers.add(provider)
    accumulator.provider_refs.append(provider_ref)
    accumulator.operations.append(operation)
    accumulator.provider_latency_ms += max(0, latency_ms)
    accumulator.tokens_in += max(0, tokens_in)
    accumulator.tokens_out += max(0, tokens_out)
    accumulator.cost_usd += max(0.0, cost_usd)
    accumulator.call_count += 1
