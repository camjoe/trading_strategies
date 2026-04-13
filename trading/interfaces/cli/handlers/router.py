from __future__ import annotations

from pathlib import Path
from typing import Any

from trading.interfaces.cli.handlers.accounts_handlers import (
    handle_apply_account_preset,
    handle_apply_account_profiles,
    handle_configure_account,
    handle_create_account,
    handle_init,
    handle_list_accounts,
    handle_set_benchmark,
    handle_trade,
)
from trading.interfaces.cli.handlers.backtesting_handlers import (
    handle_backtest,
    handle_backtest_batch,
    handle_backtest_leaderboard,
    handle_backtest_report,
    handle_backtest_walk_forward,
)
from trading.interfaces.cli.handlers.reporting_handlers import (
    handle_compare_strategies,
    handle_promotion_status,
    handle_report,
    handle_snapshot,
    handle_snapshot_history,
)


COMMAND_HANDLERS = {
    "init": handle_init,
    "create-account": handle_create_account,
    "configure-account": handle_configure_account,
    "apply-account-profiles": handle_apply_account_profiles,
    "apply-account-preset": handle_apply_account_preset,
    "set-benchmark": handle_set_benchmark,
    "list-accounts": handle_list_accounts,
    "trade": handle_trade,
    "report": handle_report,
    "promotion-status": handle_promotion_status,
    "snapshot": handle_snapshot,
    "snapshot-history": handle_snapshot_history,
    "compare-strategies": handle_compare_strategies,
    "backtest": handle_backtest,
    "backtest-report": handle_backtest_report,
    "backtest-leaderboard": handle_backtest_leaderboard,
    "backtest-batch": handle_backtest_batch,
    "backtest-walk-forward": handle_backtest_walk_forward,
}


def dispatch_command(
    conn,
    args,
    parser,
    *,
    deps: dict[str, Any],
    module_file: str,
    db_path: str | Path,
) -> None:
    command_handler = COMMAND_HANDLERS.get(args.command)
    if command_handler is None:
        parser.error(f"Unsupported command: {args.command}")
        return

    command_handler(conn, args, parser, deps=deps, module_file=module_file, db_path=db_path)
