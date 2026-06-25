from __future__ import annotations
from functools import partial
from trading.services.accounting import record_trade
from trading.services.accounts import configure_account, create_account, list_accounts, set_benchmark
from trading.backtesting.backtest import (
    backtest_leaderboard_entries,
    backtest_report,
    run_backtest,
    run_backtest_batch,
    walk_forward_report,
    run_walk_forward_backtest,
)
from infrastructure.database.init import ensure_db
from infrastructure.database.config import get_db_path
from trading.interfaces.cli.commands import build_parser
from trading.interfaces.cli.handlers.router import dispatch_command
from trading.backtesting.models import BacktestBatchConfig, BacktestConfig, WalkForwardConfig
from trading.services.profiles import apply_account_profiles, load_account_profiles
from trading.services.promotion import (
    execute_promotion_review_action,
    execute_promotion_review_request,
    show_promotion_review_history,
    show_promotion_status,
)
from infrastructure.market_data.factory import build_provider
from trading.services.reporting import account_report, compare_strategies, show_snapshots, snapshot_account


def _handler_deps() -> dict[str, object]:
    # Keep runtime dependencies explicit so handlers are testable and monkeypatch-friendly.
    # Composition root: build the market-data provider once and inject it into the
    # reporting flows that read live prices/benchmarks (no global locator access).
    provider = build_provider()
    return {
        "record_trade": record_trade,
        "configure_account": configure_account,
        "create_account": create_account,
        "list_accounts": list_accounts,
        "set_benchmark": set_benchmark,
        "BacktestBatchConfig": BacktestBatchConfig,
        "BacktestConfig": BacktestConfig,
        "WalkForwardConfig": WalkForwardConfig,
        "backtest_leaderboard_entries": backtest_leaderboard_entries,
        "backtest_report": backtest_report,
        "walk_forward_report": walk_forward_report,
        "run_backtest": run_backtest,
        "run_backtest_batch": run_backtest_batch,
        "run_walk_forward_backtest": run_walk_forward_backtest,
        "load_account_profiles": load_account_profiles,
        "apply_account_profiles": apply_account_profiles,
        "account_report": partial(account_report, provider=provider),
        "show_promotion_status": show_promotion_status,
        "execute_promotion_review_request": execute_promotion_review_request,
        "show_promotion_review_history": show_promotion_review_history,
        "execute_promotion_review_action": execute_promotion_review_action,
        "compare_strategies": partial(compare_strategies, provider=provider),
        "show_snapshots": show_snapshots,
        "snapshot_account": partial(snapshot_account, provider=provider),
    }


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    conn = ensure_db()
    try:
        dispatch_command(
            conn,
            args,
            parser,
            deps=_handler_deps(),
            module_file=__file__,
            db_path=get_db_path(),
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
