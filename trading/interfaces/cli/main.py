from trading.services.accounting_service import record_trade
from trading.services.accounts_service import configure_account, create_account, list_accounts, set_benchmark
from trading.backtesting.backtest import (
    backtest_leaderboard_entries,
    backtest_report,
    run_backtest,
    run_backtest_batch,
    run_walk_forward_backtest,
)
from trading.database.db import DB_PATH, ensure_db
from trading.interfaces.cli.commands import build_parser
from trading.interfaces.cli.handlers.shared import common_account_config_kwargs, resolve_learning_enabled
from trading.interfaces.cli.handlers.router import dispatch_command
from trading.backtesting.models import BacktestBatchConfig, BacktestConfig, WalkForwardConfig
from trading.services.profiles_service import apply_account_profiles, load_account_profiles
from trading.services.reporting_service import account_report, compare_strategies, show_snapshots, snapshot_account


def _common_account_config_kwargs(args, *, include_learning_disabled: bool):
    return common_account_config_kwargs(args, include_learning_disabled=include_learning_disabled)


def _resolve_learning_enabled(args, include_learning_disabled: bool) -> bool | None:
    return resolve_learning_enabled(args, include_learning_disabled)


def _handler_deps() -> dict[str, object]:
    # Keep runtime dependencies explicit so handlers are testable and monkeypatch-friendly.
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
        "run_backtest": run_backtest,
        "run_backtest_batch": run_backtest_batch,
        "run_walk_forward_backtest": run_walk_forward_backtest,
        "load_account_profiles": load_account_profiles,
        "apply_account_profiles": apply_account_profiles,
        "account_report": account_report,
        "compare_strategies": compare_strategies,
        "show_snapshots": show_snapshots,
        "snapshot_account": snapshot_account,
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
            db_path=DB_PATH,
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
