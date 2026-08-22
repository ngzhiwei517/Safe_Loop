"""Run the checked-in intake evaluation as a command-line quality gate."""

from __future__ import annotations

import asyncio

from app.ai.eval.runner import MINIMUM_PASS_RATE, evaluate, render_report


def main() -> int:
    report = asyncio.run(evaluate())
    print(render_report(report))
    return 0 if report.pass_rate >= MINIMUM_PASS_RATE else 1


if __name__ == "__main__":
    raise SystemExit(main())
