"""Load versioned AI prompts without allowing prompt text into Python call sites."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Final

_PROMPT_DIRECTORY: Final = Path(__file__).parent
_PROMPT_NAME: Final = re.compile(r"[a-z][a-z0-9_]*")
_VARIABLE: Final = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")


class PromptError(ValueError):
    """Reject prompt names and variables that cannot be rendered safely."""


def load_prompt(name: str) -> str:
    """Load one repository-owned Markdown prompt by its safe logical name."""
    if _PROMPT_NAME.fullmatch(name) is None:
        raise PromptError("prompt name is invalid")
    path = _PROMPT_DIRECTORY / f"{name}.md"
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as error:
        raise PromptError("prompt does not exist") from error


def _render_value(value: object) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise PromptError("prompt variable is not JSON serialisable") from error


def render_prompt(name: str, variables: dict[str, object]) -> str:
    """Render every declared placeholder and reject incomplete prompt inputs."""
    template = load_prompt(name)

    def replace(match: re.Match[str]) -> str:
        variable_name = match.group(1)
        if variable_name not in variables:
            raise PromptError("prompt variable is missing")
        return _render_value(variables[variable_name])

    rendered = _VARIABLE.sub(replace, template)
    if "{{" in rendered or "}}" in rendered:
        raise PromptError("prompt contains an invalid placeholder")
    return rendered
