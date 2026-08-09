from __future__ import annotations

from functools import partial

from backtesting.composition import (
    run_backtest,
    run_backtest_batch,
    run_backtest_metrics_only,
)
from backtesting.models import BacktestBatchConfig, BacktestConfig
from backtesting.models.optimizer import OptimizerConfig
from backtesting.services.audit import fetch_experiment_audit
from backtesting.services.optimization_experiment import run_and_persist_optimization
from backtesting.services.reporting import fetch_leaderboard, fetch_report
from infrastructure.database.config import get_db_path
from infrastructure.database.connection import db_session
from infrastructure.market_data.factory import build_provider, resolve_provider_name
from trading.domain.promotion_gate import evaluate_promotion_gate
from trading.interfaces.cli.commands import build_parser
from trading.interfaces.cli.handlers.router import dispatch_command
from trading.services.accounts import configure_account, create_account, list_accounts, set_benchmark
from trading.services.execution.ledger import record_trade
from trading.services.operational_settings import (
    fetch_evaluation_confidence_settings,
    fetch_promotion_policy_settings,
    fetch_runtime_throttle_settings,
    set_evaluation_confidence_settings,
    set_promotion_policy_settings,
    set_runtime_throttle_settings,
    show_global_settings_history,
)
from trading.services.parameters import (
    show_book_rotation_history,
    show_parameters,
    update_book_rotation_policy,
    update_book_rotation_scheduling,
)
from trading.services.promotion import (
    execute_promotion_review_action,
    execute_promotion_review_request,
    show_promotion_review_history,
    show_promotion_status,
)
from trading.services.reporting import (
    account_report,
    compare_strategies,
    show_portfolio_concentration,
    show_portfolio_exposure,
    show_snapshots,
    snapshot_account,
)
from trading.services.strategy_catalog import (
    configure_strategy,
    create_strategy_variant,
    freeze_strategy,
    promote_optimization_experiment,
)


def _handler_deps() -> dict[str, object]:
    # Keep runtime dependencies explicit so handlers are testable and monkeypatch-friendly.
    # Composition root: build the market-data provider once per invocation and inject
    # it into every flow that reads prices (no global locator access). One instance
    # per invocation is what makes the adapter's cumulative call guard mean anything
    # — an optimizer sweep runs a backtest per candidate, per window.
    provider = build_provider()
    return {
        "db_path": get_db_path(),
        "record_trade": record_trade,
        "configure_account": configure_account,
        "create_account": create_account,
        "list_accounts": list_accounts,
        "set_benchmark": set_benchmark,
        "BacktestBatchConfig": BacktestBatchConfig,
        "BacktestConfig": BacktestConfig,
        "OptimizerConfig": OptimizerConfig,
        "fetch_leaderboard": fetch_leaderboard,
        "fetch_report": fetch_report,
        "run_backtest": partial(run_backtest, provider=provider),
        "run_backtest_metrics_only": partial(run_backtest_metrics_only, provider=provider),
        "run_backtest_batch": partial(run_backtest_batch, provider=provider),
        "run_and_persist_optimization": partial(
            run_and_persist_optimization, market_data_provider=resolve_provider_name()
        ),
        "fetch_experiment_audit": fetch_experiment_audit,
        "evaluate_promotion_gate": evaluate_promotion_gate,
        "promote_optimization_experiment": promote_optimization_experiment,
        "account_report": partial(account_report, provider=provider),
        "show_promotion_status": show_promotion_status,
        "execute_promotion_review_request": execute_promotion_review_request,
        "show_promotion_review_history": show_promotion_review_history,
        "execute_promotion_review_action": execute_promotion_review_action,
        "compare_strategies": partial(compare_strategies, provider=provider),
        "show_parameters": show_parameters,
        "fetch_runtime_throttle_settings": fetch_runtime_throttle_settings,
        "fetch_evaluation_confidence_settings": fetch_evaluation_confidence_settings,
        "fetch_promotion_policy_settings": fetch_promotion_policy_settings,
        "set_runtime_throttle_settings": set_runtime_throttle_settings,
        "set_evaluation_confidence_settings": set_evaluation_confidence_settings,
        "set_promotion_policy_settings": set_promotion_policy_settings,
        "update_book_rotation_policy": update_book_rotation_policy,
        "update_book_rotation_scheduling": update_book_rotation_scheduling,
        "show_global_settings_history": show_global_settings_history,
        "show_book_rotation_history": show_book_rotation_history,
        "configure_strategy": configure_strategy,
        "create_strategy_variant": create_strategy_variant,
        "freeze_strategy": freeze_strategy,
        "show_portfolio_concentration": show_portfolio_concentration,
        "show_portfolio_exposure": show_portfolio_exposure,
        "show_snapshots": show_snapshots,
        "snapshot_account": partial(snapshot_account, provider=provider),
    }


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    with db_session() as conn:
        dispatch_command(conn, args, parser, deps=_handler_deps())


if __name__ == "__main__":
    main()
