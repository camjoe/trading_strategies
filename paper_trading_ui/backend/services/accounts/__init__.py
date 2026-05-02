"""Stable local import surface for paper_trading_ui account service helpers.

External callers within ``paper_trading_ui.backend`` should keep importing from
``paper_trading_ui.backend.services.accounts``. The submodules under this
package are the internal split by responsibility.

Account-name and snapshot-row queries delegate to canonical trading service
function names directly rather than through local wrapper aliases.
"""

from __future__ import annotations

from .backtests import (
    fetch_latest_backtest_metrics,
    fetch_latest_backtest_summary,
    fetch_recent_backtest_run_summaries,
)
from .benchmark import (
    attach_live_benchmark_summary,
    build_live_benchmark_overlay,
)
from .data_access import (
    build_snapshot_payload,
    build_trade_payload,
    require_account_row,
    fetch_visible_account_rows,
)
from .mutations import update_account_params
from .summaries import (
    _build_positions_from_stats,  # noqa: F401  accessed by tests via module attribute
    build_account_list_payload,
    build_account_summary,
    build_account_summary_and_positions,
    build_comparison_account_payload,
)

__all__ = [
    "attach_live_benchmark_summary",
    "build_account_list_payload",
    "build_account_summary",
    "build_account_summary_and_positions",
    "build_comparison_account_payload",
    "build_live_benchmark_overlay",
    "build_snapshot_payload",
    "build_trade_payload",
    "fetch_latest_backtest_metrics",
    "fetch_latest_backtest_summary",
    "require_account_row",
    "fetch_visible_account_rows",
    "fetch_recent_backtest_run_summaries",
    "update_account_params",
]
