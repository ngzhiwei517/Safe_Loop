"""Run the paid ASR corpus explicitly outside CI."""

from __future__ import annotations

import argparse
import asyncio
import os

from app.ai.transcription import (
    GeminiTranscription,
    GeminiTranscriptionConfig,
    StubTranscription,
    TranscriptionProvider,
)
from app.ai.live_transcription import GeminiLiveFileTranscription, LiveTranscriptionConfig
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
        choices=("vertex", "live", "stub"),
        default="vertex",
        help="Vertex is the quality evaluation; stub only checks harness plumbing.",
    )
    args = parser.parse_args()
    settings = get_settings()
    provider: TranscriptionProvider
    if args.provider == "stub":
        provider = StubTranscription()
    elif args.provider == "live":
        provider = GeminiLiveFileTranscription(
            LiveTranscriptionConfig.from_settings(settings)
        )
    else:
        provider = GeminiTranscription(
            GeminiTranscriptionConfig.from_settings(settings)
        )
    print(render_report(asyncio.run(evaluate(provider))))


if __name__ == "__main__":
    main()
