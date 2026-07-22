"""Benchmark overlay helpers — thin re-export shim.

Domain logic lives in ``trading.services.analysis.benchmark``.
This module re-exports the public surface so callers within
``paper_trading_web.backend`` can import from a stable local path.
"""

from __future__ import annotations

from trading.services.analysis.benchmark import (  # noqa: F401
    attach_live_benchmark_summary,
    build_live_benchmark_overlay,
    fetch_benchmark_close_history,
)

__all__ = [
    "attach_live_benchmark_summary",
    "build_live_benchmark_overlay",
    "fetch_benchmark_close_history",
]
