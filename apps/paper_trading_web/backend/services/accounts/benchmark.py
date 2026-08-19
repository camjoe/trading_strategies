"""Benchmark overlay web helpers.

The overlay computation lives in ``trading.services.analysis.benchmark`` and
returns a snake_case payload; the camelCase summary shaping for the frontend is
the web boundary's job and lives here (UI Backend Boundary Rule).
"""

from __future__ import annotations

from typing import Any

from trading.services.analysis.benchmark import (  # noqa: F401
    build_live_benchmark_overlay,
    fetch_benchmark_close_history,
)


def build_live_benchmark_overlay_payload(overlay: dict[str, Any] | None) -> dict[str, object] | None:
    """camelCase the snake_case overlay for the frontend, or pass ``None`` through."""
    if overlay is None:
        return None
    return {
        "benchmark": overlay["benchmark"],
        "startTime": overlay["start_time"],
        "endTime": overlay["end_time"],
        "startingEquity": overlay["starting_equity"],
        "endingEquity": overlay["ending_equity"],
        "benchmarkEquity": overlay["benchmark_equity"],
        "accountReturnPct": overlay["account_return_pct"],
        "benchmarkReturnPct": overlay["benchmark_return_pct"],
        "alphaPct": overlay["alpha_pct"],
        "points": [
            {
                "time": point["time"],
                "accountEquity": point["account_equity"],
                "benchmarkEquity": point["benchmark_equity"],
            }
            for point in overlay["points"]
        ],
    }


def attach_live_benchmark_summary(
    summary: dict[str, object],
    overlay: dict[str, object] | None,
) -> dict[str, object]:
    """Inject camelCase benchmark summary fields into *summary* from *overlay*.

    Reads the snake_case overlay and sets ``liveBenchmark*`` keys on the
    (camelCase) account summary. All fields are ``None`` when *overlay* is
    ``None`` (benchmark unavailable).
    """
    summary["liveBenchmarkReturnPct"] = overlay["benchmark_return_pct"] if overlay is not None else None
    summary["liveAlphaPct"] = overlay["alpha_pct"] if overlay is not None else None
    summary["liveBenchmarkEquity"] = overlay["benchmark_equity"] if overlay is not None else None
    summary["liveBenchmarkStartTime"] = overlay["start_time"] if overlay is not None else None
    summary["liveBenchmarkEndTime"] = overlay["end_time"] if overlay is not None else None
    return summary


__all__ = [
    "attach_live_benchmark_summary",
    "build_live_benchmark_overlay",
    "build_live_benchmark_overlay_payload",
    "fetch_benchmark_close_history",
]
