"""Keep deterministic test AI and future model providers behind one typed boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from hashlib import sha256
import json
from math import ceil, floor
import os
from collections.abc import Callable
from typing import Final, Protocol, TypeAlias, cast
from uuid import UUID

from pydantic import BaseModel, ValidationError

from app.ai.prompts import render_prompt
from app.config import get_settings

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
Vector: TypeAlias = list[float]

EMBEDDING_DIMENSIONS: Final = 1536


@dataclass(frozen=True)
class ProviderResult:
    """Preserve structured output together with the evidence needed to audit one run."""

    data: dict[str, JsonValue]
    raw: str
    provider: str
    provider_ref: str
    latency_ms: int
    tokens_in: int
    tokens_out: int


class AIProvider(Protocol):
    """Define all model access used by graph nodes and retrieval code."""

    async def complete(
        self,
        prompt_name: str,
        variables: dict[str, object],
        *,
        schema: type[BaseModel],
    ) -> ProviderResult: ...

    async def embed(self, texts: list[str]) -> list[Vector]: ...


class ProviderConfigurationError(RuntimeError):
    """Fail closed when a provider was not explicitly selected."""


class StubSchemaError(ValueError):
    """Expose unsupported schema shapes instead of returning invalid fake data."""


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str) or type(value) in {int, float, bool}:
        return cast(JsonScalar, value)
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {str(key): _json_value(item) for key, item in value.items()}
    raise StubSchemaError("value is not JSON serialisable")


def _object(value: object, *, context: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise StubSchemaError(f"{context} must be an object")
    return {str(key): item for key, item in value.items()}


class _FixtureBuilder:
    def __init__(self, root: dict[str, object], seed: str) -> None:
        self._root = root
        self._seed = seed

    def _digest(self, path: str) -> str:
        return sha256(f"{self._seed}:{path}".encode()).hexdigest()

    def _resolve(self, reference: str) -> dict[str, object]:
        if not reference.startswith("#/"):
            raise StubSchemaError("only local schema references are supported")
        current: object = self._root
        for raw_part in reference[2:].split("/"):
            part = raw_part.replace("~1", "/").replace("~0", "~")
            current = _object(current, context="schema reference").get(part)
            if current is None:
                raise StubSchemaError("schema reference does not exist")
        return _object(current, context="schema reference")

    def build(self, schema_value: object, path: str = "$", depth: int = 0) -> JsonValue:
        if depth > 16:
            raise StubSchemaError("schema nesting is too deep")
        schema = _object(schema_value, context="schema")

        reference = schema.get("$ref")
        if isinstance(reference, str):
            return self.build(self._resolve(reference), path, depth + 1)

        constant = schema.get("const")
        if "const" in schema:
            return _json_value(constant)

        enum = schema.get("enum")
        if isinstance(enum, list) and enum:
            index = int(self._digest(path)[:8], 16) % len(enum)
            return _json_value(enum[index])

        for union_key in ("anyOf", "oneOf"):
            choices = schema.get(union_key)
            if isinstance(choices, list) and choices:
                non_null = [
                    choice
                    for choice in choices
                    if not (
                        isinstance(choice, dict)
                        and choice.get("type") == "null"
                    )
                ]
                return self.build(
                    non_null[0] if non_null else choices[0],
                    f"{path}.{union_key}",
                    depth + 1,
                )

        all_of = schema.get("allOf")
        if isinstance(all_of, list) and all_of:
            return self.build(all_of[0], f"{path}.allOf", depth + 1)

        value_type = schema.get("type")
        if isinstance(value_type, list):
            value_type = next(
                (candidate for candidate in value_type if candidate != "null"),
                "null",
            )
        if value_type is None and isinstance(schema.get("properties"), dict):
            value_type = "object"

        if value_type == "object":
            properties = _object(schema.get("properties", {}), context="schema properties")
            raw_required = schema.get("required", [])
            if not isinstance(raw_required, list) or not all(
                isinstance(item, str) for item in raw_required
            ):
                raise StubSchemaError("schema required fields are invalid")
            return {
                field_name: self.build(
                    properties[field_name],
                    f"{path}.{field_name}",
                    depth + 1,
                )
                for field_name in raw_required
                if field_name in properties
            }

        if value_type == "array":
            minimum = _integer_keyword(schema.get("minItems"), default=0)
            maximum = _integer_keyword(schema.get("maxItems"), default=max(1, minimum))
            if maximum < minimum:
                raise StubSchemaError("array bounds are invalid")
            count = min(maximum, max(1, minimum)) if maximum > 0 else 0
            item_schema = schema.get("items", {"type": "string"})
            return [
                self.build(item_schema, f"{path}[{index}]", depth + 1)
                for index in range(count)
            ]

        if value_type == "string":
            return self._string(schema, path)
        if value_type == "integer":
            return self._integer(schema, path)
        if value_type == "number":
            return self._number(schema, path)
        if value_type == "boolean":
            return int(self._digest(path)[:2], 16) % 2 == 0
        if value_type == "null":
            return None
        raise StubSchemaError("schema type is unsupported")

    def _string(self, schema: dict[str, object], path: str) -> str:
        digest = self._digest(path)
        string_format = schema.get("format")
        if string_format == "uuid":
            return str(UUID(hex=digest[:32]))
        if string_format == "date-time":
            return datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
        if string_format == "date":
            return date(2026, 1, 1).isoformat()
        if string_format == "time":
            return time(9, 0, tzinfo=timezone.utc).isoformat()

        minimum = _integer_keyword(schema.get("minLength"), default=1)
        maximum = _integer_keyword(
            schema.get("maxLength"),
            default=max(minimum, 17),
        )
        if maximum < minimum:
            raise StubSchemaError("string bounds are invalid")
        value = f"stub-{digest[:12]}"
        while len(value) < minimum:
            value += digest
        return value[:maximum]

    def _integer(self, schema: dict[str, object], path: str) -> int:
        lower = _numeric_keyword(schema.get("minimum"), default=0.0)
        upper = _numeric_keyword(schema.get("maximum"), default=lower + 100.0)
        if "exclusiveMinimum" in schema:
            lower = _numeric_keyword(schema["exclusiveMinimum"], default=lower) + 1
        if "exclusiveMaximum" in schema:
            upper = _numeric_keyword(schema["exclusiveMaximum"], default=upper) - 1
        low_integer = ceil(lower)
        high_integer = floor(upper)
        if high_integer < low_integer:
            raise StubSchemaError("integer bounds are invalid")
        return low_integer + int(self._digest(path)[:8], 16) % (
            high_integer - low_integer + 1
        )

    def _number(self, schema: dict[str, object], path: str) -> float:
        lower = _numeric_keyword(schema.get("minimum"), default=0.0)
        upper = _numeric_keyword(schema.get("maximum"), default=lower + 1.0)
        if "exclusiveMinimum" in schema:
            lower = _numeric_keyword(schema["exclusiveMinimum"], default=lower)
        if "exclusiveMaximum" in schema:
            upper = _numeric_keyword(schema["exclusiveMaximum"], default=upper)
        if upper <= lower:
            raise StubSchemaError("number bounds are invalid")
        fraction = int(self._digest(path)[:12], 16) / float(0xFFFFFFFFFFFF)
        return round(lower + (upper - lower) * fraction, 8)


def _integer_keyword(value: object, *, default: int) -> int:
    if type(value) is int:
        return value
    return default


def _numeric_keyword(value: object, *, default: float) -> float:
    if type(value) in {int, float}:
        return float(cast(int | float, value))
    return default


class StubProvider:
    """Produce repeatable schema-validated output without any external side effect."""

    provider_name: Final = "stub"

    def __init__(self, *, selected_provider: str | None = None) -> None:
        configured = selected_provider or os.environ.get("AI_PROVIDER")
        if configured != self.provider_name:
            raise ProviderConfigurationError("AI_PROVIDER must be explicitly set to stub")

    async def complete(
        self,
        prompt_name: str,
        variables: dict[str, object],
        *,
        schema: type[BaseModel],
    ) -> ProviderResult:
        rendered_prompt = render_prompt(prompt_name, variables)
        schema_definition = cast(dict[str, object], schema.model_json_schema())
        canonical_input = json.dumps(
            {
                "prompt_name": prompt_name,
                "prompt": rendered_prompt,
                "schema": schema_definition,
                "variables": _json_value(variables),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        seed = sha256(canonical_input.encode()).hexdigest()
        fixture_factory = cast(
            Callable[[dict[str, object]], dict[str, JsonValue]] | None,
            getattr(schema, "stub_fixture", None),
        )
        fixture: JsonValue
        if fixture_factory is None:
            fixture = _FixtureBuilder(schema_definition, seed).build(schema_definition)
        else:
            fixture = fixture_factory(dict(variables))
        if not isinstance(fixture, dict):
            raise StubSchemaError("completion schema must produce an object")
        try:
            validated = schema.model_validate(fixture)
        except ValidationError as error:
            raise StubSchemaError("stub could not satisfy the completion schema") from error
        data_value = _json_value(validated.model_dump(mode="json"))
        if not isinstance(data_value, dict):
            raise StubSchemaError("completion schema must serialise to an object")
        raw = json.dumps(
            data_value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return ProviderResult(
            data=data_value,
            raw=raw,
            provider=self.provider_name,
            provider_ref=f"stub-{seed[:24]}",
            latency_ms=int(seed[:4], 16) % 25,
            tokens_in=max(1, (len(rendered_prompt.encode("utf-8")) + 3) // 4),
            tokens_out=max(1, (len(raw.encode("utf-8")) + 3) // 4),
        )

    async def embed(self, texts: list[str]) -> list[Vector]:
        vectors: list[Vector] = []
        for text in texts:
            seed = sha256(text.encode()).digest()
            values: Vector = []
            block_index = 0
            while len(values) < EMBEDDING_DIMENSIONS:
                block = sha256(seed + block_index.to_bytes(4, "big")).digest()
                values.extend(round((byte / 127.5) - 1.0, 8) for byte in block)
                block_index += 1
            vectors.append(values[:EMBEDDING_DIMENSIONS])
        return vectors


def get_provider() -> AIProvider:
    """Select only configured implementations and reject silent production fallbacks."""
    provider_name = get_settings().ai_provider.strip().lower()
    if provider_name == StubProvider.provider_name:
        return StubProvider(selected_provider=provider_name)
    raise ProviderConfigurationError("configured AI_PROVIDER is not implemented")
