from __future__ import annotations

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
    handle_backtest_optimize,
    handle_backtest_optimize_promote,
    handle_backtest_optimize_show,
    handle_backtest_report,
)
from trading.interfaces.cli.handlers.reporting_handlers import (
    handle_compare_strategies,
    handle_parameters,
    handle_portfolio_concentration,
    handle_portfolio_exposure,
    handle_promotion_request_review,
    handle_promotion_review_action,
    handle_promotion_review_history,
    handle_promotion_status,
    handle_report,
    handle_snapshot,
    handle_snapshot_history,
)
from trading.interfaces.cli.handlers.settings_handlers import (
    handle_book_rotation_history,
    handle_configure_book_rotation,
    handle_configure_book_rotation_policy,
    handle_configure_evaluation,
    handle_configure_promotion,
    handle_configure_throttle,
    handle_settings_history,
)
from trading.interfaces.cli.handlers.strategy_catalog_handlers import (
    handle_configure_strategy,
    handle_create_strategy_variant,
    handle_freeze_strategy,
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
    "promotion-request-review": handle_promotion_request_review,
    "promotion-review-history": handle_promotion_review_history,
    "promotion-review-action": handle_promotion_review_action,
    "snapshot": handle_snapshot,
    "snapshot-history": handle_snapshot_history,
    "compare-strategies": handle_compare_strategies,
    "portfolio-exposure": handle_portfolio_exposure,
    "portfolio-concentration": handle_portfolio_concentration,
    "parameters": handle_parameters,
    "configure-throttle": handle_configure_throttle,
    "configure-evaluation": handle_configure_evaluation,
    "configure-promotion": handle_configure_promotion,
    "configure-book-rotation": handle_configure_book_rotation,
    "configure-book-rotation-policy": handle_configure_book_rotation_policy,
    "settings-history": handle_settings_history,
    "book-rotation-history": handle_book_rotation_history,
    "create-strategy-variant": handle_create_strategy_variant,
    "configure-strategy": handle_configure_strategy,
    "freeze-strategy": handle_freeze_strategy,
    "backtest": handle_backtest,
    "backtest-report": handle_backtest_report,
    "backtest-leaderboard": handle_backtest_leaderboard,
    "backtest-batch": handle_backtest_batch,
    "backtest-optimize": handle_backtest_optimize,
    "backtest-optimize-show": handle_backtest_optimize_show,
    "backtest-optimize-promote": handle_backtest_optimize_promote,
}


def dispatch_command(
    conn,
    args,
    parser,
    *,
    deps: dict[str, Any],
) -> None:
    command_handler = COMMAND_HANDLERS.get(args.command)
    if command_handler is None:
        parser.error(f"Unsupported command: {args.command}")
        return

    command_handler(conn, args, parser, deps=deps)
