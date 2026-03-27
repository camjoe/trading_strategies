from pathlib import Path
from typing import Callable
from trading.accounting import record_trade
from trading.accounts import configure_account, create_account, list_accounts, set_benchmark
from trading.backtesting.backtest import (
    BacktestBatchConfig,
    BacktestConfig,
    WalkForwardConfig,
    backtest_leaderboard,
    backtest_report,
    run_backtest,
    run_backtest_batch,
    run_walk_forward_backtest,
)
from trading.cli_commands import build_parser
from trading.database.db import DB_PATH, ensure_db
from trading.profiles import apply_account_profiles, load_account_profiles
from trading.reporting import account_report, compare_strategies, show_snapshots, snapshot_account


def _common_account_config_kwargs(args, *, include_learning_disabled: bool) -> dict:
    learning_enabled = _resolve_learning_enabled(args, include_learning_disabled)

    return {
        "descriptive_name": args.display_name,
        "goal_min_return_pct": args.goal_min_return_pct,
        "goal_max_return_pct": args.goal_max_return_pct,
        "goal_period": args.goal_period,
        "learning_enabled": learning_enabled,
        "risk_policy": args.risk_policy,
        "stop_loss_pct": args.stop_loss_pct,
        "take_profit_pct": args.take_profit_pct,
        "instrument_mode": args.instrument_mode,
        "option_strike_offset_pct": args.option_strike_offset_pct,
        "option_min_dte": args.option_min_dte,
        "option_max_dte": args.option_max_dte,
        "option_type": args.option_type,
        "target_delta_min": args.target_delta_min,
        "target_delta_max": args.target_delta_max,
        "max_premium_per_trade": args.max_premium_per_trade,
        "max_contracts_per_trade": args.max_contracts_per_trade,
        "iv_rank_min": args.iv_rank_min,
        "iv_rank_max": args.iv_rank_max,
        "roll_dte_threshold": args.roll_dte_threshold,
        "profit_take_pct": args.profit_take_pct,
        "max_loss_pct": args.max_loss_pct,
    }


def _resolve_learning_enabled(args, include_learning_disabled: bool) -> bool | None:
    if include_learning_disabled:
        if args.learning_enabled and args.learning_disabled:
            raise ValueError("Use only one of --learning-enabled or --learning-disabled")
        if args.learning_enabled:
            return True
        if args.learning_disabled:
            return False
        return None
    return bool(args.learning_enabled)


def _print_profiles_result(prefix: str, created: int, updated: int, skipped: int) -> None:
    print(f"{prefix}created={created}, updated={updated}, skipped={skipped}.")


def _handle_init(conn, args, parser) -> None:
    print(f"Initialized: {DB_PATH}")


def _handle_create_account(conn, args, parser) -> None:
    create_account(
        conn,
        args.name,
        args.strategy,
        args.initial_cash,
        args.benchmark,
        **_common_account_config_kwargs(args, include_learning_disabled=False),
    )
    print(
        f"Created account '{args.name}' for strategy '{args.strategy}' "
        f"with benchmark '{args.benchmark.upper()}'."
    )


def _handle_configure_account(conn, args, parser) -> None:
    try:
        config_kwargs = _common_account_config_kwargs(args, include_learning_disabled=True)
    except ValueError as error:
        parser.error(str(error))

    configure_account(
        conn,
        account_name=args.account,
        **config_kwargs,
    )
    print(f"Updated account configuration for '{args.account}'.")


def _handle_apply_account_profiles(conn, args, parser) -> None:
    profiles = load_account_profiles(args.file)
    created, updated, skipped = apply_account_profiles(
        conn,
        profiles,
        create_missing=not args.no_create_missing,
    )
    _print_profiles_result("Applied account profiles: ", created, updated, skipped)


def _handle_apply_account_preset(conn, args, parser) -> None:
    preset_file = (
        Path(__file__).resolve().parent
        / "account_profiles"
        / f"{args.preset.strip().lower()}.json"
    )
    profiles = load_account_profiles(str(preset_file))
    created, updated, skipped = apply_account_profiles(
        conn,
        profiles,
        create_missing=not args.no_create_missing,
    )
    _print_profiles_result(f"Applied preset '{args.preset}': ", created, updated, skipped)


def _handle_set_benchmark(conn, args, parser) -> None:
    set_benchmark(conn, args.account, args.benchmark)
    print(f"Updated benchmark for '{args.account}' to '{args.benchmark.upper()}'.")


def _handle_list_accounts(conn, args, parser) -> None:
    list_accounts(conn)


def _handle_trade(conn, args, parser) -> None:
    record_trade(
        conn,
        account_name=args.account,
        side=args.side,
        ticker=args.ticker,
        qty=args.qty,
        price=args.price,
        fee=args.fee,
        trade_time=args.time,
        note=args.note,
    )
    print("Trade recorded.")


def _handle_report(conn, args, parser) -> None:
    account_report(conn, args.account)


def _handle_snapshot(conn, args, parser) -> None:
    snapshot_account(conn, args.account, args.time)


def _handle_snapshot_history(conn, args, parser) -> None:
    show_snapshots(conn, args.account, args.limit)


def _handle_compare_strategies(conn, args, parser) -> None:
    compare_strategies(conn, args.lookback)


def _handle_backtest(conn, args, parser) -> None:
    result = run_backtest(
        conn,
        BacktestConfig(
            account_name=args.account,
            tickers_file=args.tickers_file,
            universe_history_dir=args.universe_history_dir,
            start=args.start,
            end=args.end,
            lookback_months=args.lookback_months,
            slippage_bps=args.slippage_bps,
            fee_per_trade=args.fee,
            run_name=args.run_name,
            allow_approximate_leaps=bool(args.allow_approximate_leaps),
        ),
    )
    print(
        f"Backtest complete: run_id={result.run_id} account={result.account_name} "
        f"range={result.start_date}..{result.end_date} trades={result.trade_count}"
    )
    print(
        f"Ending Equity: {result.ending_equity:.2f} | Return: {result.total_return_pct:.2f}% | "
        f"Max Drawdown: {result.max_drawdown_pct:.2f}%"
    )
    if result.benchmark_return_pct is not None and result.alpha_pct is not None:
        print(
            f"Benchmark Return: {result.benchmark_return_pct:.2f}% | Alpha: {result.alpha_pct:.2f}%"
        )
    else:
        print("Benchmark comparison unavailable for selected date range.")

    if result.warnings:
        print("Backtest safeguards / approximation notes:")
        for warning in result.warnings:
            print(f"- {warning}")


def _handle_backtest_report(conn, args, parser) -> None:
    report = backtest_report(conn, args.run_id)
    print(
        f"Backtest Run {report['run_id']} ({report['run_name'] or 'unnamed'}) | "
        f"account={report['account_name']} strategy={report['strategy']}"
    )
    print(
        f"Range: {report['start_date']}..{report['end_date']} | Created: {report['created_at']} "
        f"| Trades: {report['trade_count']}"
    )
    print(
        f"Start Equity: {report['starting_equity']:.2f} | End Equity: {report['ending_equity']:.2f} "
        f"| Return: {report['total_return_pct']:.2f}% | Max DD: {report['max_drawdown_pct']:.2f}%"
    )
    print(
        f"Slippage (bps): {report['slippage_bps']:.2f} | Fee/Trade: {report['fee_per_trade']:.2f} "
        f"| Tickers File: {report['tickers_file']}"
    )
    if report["warnings"]:
        print(f"Safeguards / notes: {report['warnings']}")


def _handle_backtest_leaderboard(conn, args, parser) -> None:
    rows = backtest_leaderboard(
        conn,
        limit=int(args.limit),
        account_name=args.account,
        strategy=args.strategy,
    )

    if not rows:
        print("No backtest runs matched the selected filters.")
        return

    print(
        "run_id,run_name,account_name,strategy,start_date,end_date,ending_equity,"
        "total_return_pct,max_drawdown_pct,benchmark_return_pct,alpha_pct,trade_count,created_at"
    )
    for row in rows:
        benchmark_return = row["benchmark_return_pct"]
        alpha = row["alpha_pct"]
        benchmark_text = "" if benchmark_return is None else f"{float(benchmark_return):.4f}"
        alpha_text = "" if alpha is None else f"{float(alpha):.4f}"
        run_name = "" if row["run_name"] is None else str(row["run_name"])
        print(
            f"{row['run_id']},{run_name},{row['account_name']},{row['strategy']},"
            f"{row['start_date']},{row['end_date']},{float(row['ending_equity']):.2f},"
            f"{float(row['total_return_pct']):.4f},{float(row['max_drawdown_pct']):.4f},"
            f"{benchmark_text},{alpha_text},{int(row['trade_count'])},{row['created_at']}"
        )


def _handle_backtest_batch(conn, args, parser) -> None:
    account_names = [name.strip() for name in args.accounts.split(",") if name.strip()]
    results = run_backtest_batch(
        conn,
        BacktestBatchConfig(
            account_names=account_names,
            tickers_file=args.tickers_file,
            universe_history_dir=args.universe_history_dir,
            start=args.start,
            end=args.end,
            lookback_months=args.lookback_months,
            slippage_bps=args.slippage_bps,
            fee_per_trade=args.fee,
            run_name_prefix=args.run_name_prefix,
            allow_approximate_leaps=bool(args.allow_approximate_leaps),
        ),
    )

    print("Backtest batch complete.")
    print("rank,account_name,run_id,total_return_pct,max_drawdown_pct,ending_equity,trade_count")
    for rank, result in enumerate(results, start=1):
        print(
            f"{rank},{result.account_name},{result.run_id},{result.total_return_pct:.4f},"
            f"{result.max_drawdown_pct:.4f},{result.ending_equity:.2f},{result.trade_count}"
        )


def _handle_backtest_walk_forward(conn, args, parser) -> None:
    summary = run_walk_forward_backtest(
        conn,
        WalkForwardConfig(
            account_name=args.account,
            tickers_file=args.tickers_file,
            universe_history_dir=args.universe_history_dir,
            start=args.start,
            end=args.end,
            lookback_months=args.lookback_months,
            test_months=args.test_months,
            step_months=args.step_months,
            slippage_bps=args.slippage_bps,
            fee_per_trade=args.fee,
            run_name_prefix=args.run_name_prefix,
            allow_approximate_leaps=bool(args.allow_approximate_leaps),
        ),
    )

    print(
        f"Walk-forward complete: account={summary.account_name} range={summary.start_date}..{summary.end_date} "
        f"windows={summary.window_count}"
    )
    print(
        f"Average Return: {summary.average_return_pct:.2f}% | Median Return: {summary.median_return_pct:.2f}% "
        f"| Best: {summary.best_return_pct:.2f}% | Worst: {summary.worst_return_pct:.2f}%"
    )
    run_ids_preview = ", ".join([str(run_id) for run_id in summary.run_ids[:10]])
    if len(summary.run_ids) > 10:
        run_ids_preview += ", ..."
    print(f"Generated run ids: {run_ids_preview}")


COMMAND_HANDLERS: dict[str, Callable] = {
    "init": _handle_init,
    "create-account": _handle_create_account,
    "configure-account": _handle_configure_account,
    "apply-account-profiles": _handle_apply_account_profiles,
    "apply-account-preset": _handle_apply_account_preset,
    "set-benchmark": _handle_set_benchmark,
    "list-accounts": _handle_list_accounts,
    "trade": _handle_trade,
    "report": _handle_report,
    "snapshot": _handle_snapshot,
    "snapshot-history": _handle_snapshot_history,
    "compare-strategies": _handle_compare_strategies,
    "backtest": _handle_backtest,
    "backtest-report": _handle_backtest_report,
    "backtest-leaderboard": _handle_backtest_leaderboard,
    "backtest-batch": _handle_backtest_batch,
    "backtest-walk-forward": _handle_backtest_walk_forward,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    conn = ensure_db()
    try:
        command_handler = COMMAND_HANDLERS.get(args.command)
        if command_handler is None:
            parser.error(f"Unsupported command: {args.command}")
            return
        command_handler(conn, args, parser)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
