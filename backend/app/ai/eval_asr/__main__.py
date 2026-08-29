"""Run the paid ASR corpus explicitly outside CI."""

from __future__ import annotations

import argparse
import asyncio
import os

from app.ai.transcription import (
    GeminiTranscription,
    GeminiTranscriptionConfig,
    StubTranscription,
)
from app.ai.eval_asr.runner import evaluate, render_report
from app.config import get_settings


def main() -> None:
    if os.environ.get("CI"):
        raise SystemExit("ASR evaluation is intentionally disabled in CI")
    parser = argparse.ArgumentParser(
        description="Run the committed SafeLoop speech corpus outside CI.",
    )
    parser.add_argument(
        "--provider",
        choices=("vertex", "stub"),
        default="vertex",
        help="Vertex is the quality evaluation; stub only checks harness plumbing.",
    )
    args = parser.parse_args()
    provider = (
        StubTranscription()
        if args.provider == "stub"
        else GeminiTranscription(
            GeminiTranscriptionConfig.from_settings(get_settings())
        )
    )
    print(render_report(asyncio.run(evaluate(provider))))


if __name__ == "__main__":
    main()
