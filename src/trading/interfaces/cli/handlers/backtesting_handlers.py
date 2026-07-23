from __future__ import annotations

import json
from typing import Any


def _format_metric(value: float | None, *, suffix: str = "") -> str:
    return "n/a" if value is None else f"{value:.2f}{suffix}"


def _target_age_label(target: Any) -> str:
    return "missing" if target.age_days is None else f"{target.age_days:.1f}d"


def handle_refresh_stale_backtests(conn, args, parser, *, deps: dict[str, Any]) -> None:
    targets = deps["find_stale_backtests"](conn, account_name=args.account)
    if args.limit is not None:
        targets = targets[: max(0, args.limit)]

    if not targets:
        print("No stale or missing backtests found.")
        return

    if args.dry_run:
        print(f"{len(targets)} stale/missing backtest target(s):")
        for target in targets:
            print(f"  {target.account_name}/{target.strategy_name} ({target.reason}, {_target_age_label(target)})")
        return

    refreshed = 0
    failed = 0
    for target in targets:
        try:
            result = deps["run_backtest"](
                conn,
                deps["BacktestConfig"](
                    account_name=target.account_name,
                    tickers_file=args.tickers_file,
                    universe_history_dir=args.universe_history_dir,
                    start=args.start,
                    end=args.end,
                    lookback_months=args.lookback_months,
                    slippage_bps=args.slippage_bps,
                    fee_per_trade=args.fee,
                    run_name=f"refresh_{target.strategy_name}",
                    allow_approximate_leaps=bool(args.allow_approximate_leaps),
                    strategy=target.strategy_name,
                ),
            )
        except Exception as error:  # noqa: BLE001 - one bad target must not abort the batch
            print(f"Failed {target.account_name}/{target.strategy_name}: {error}")
            failed += 1
            continue
        print(f"Refreshed {target.account_name}/{target.strategy_name}: run_id={result.run_id}")
        refreshed += 1

    print(f"Done: {refreshed} refreshed, {failed} failed.")


def handle_backtest(conn, args, parser, *, deps: dict[str, Any]) -> None:
    try:
        result = deps["run_backtest"](
            conn,
            deps["BacktestConfig"](
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
                strategy=args.strategy,
            ),
        )
    except ValueError as error:
        parser.error(str(error))
        return
    print(
        f"Backtest complete: run_id={result.run_id} account={result.account_name} "
        f"range={result.start_date}..{result.end_date} trades={result.trade_count}"
    )
    print(
        f"Ending Equity: {result.ending_equity:.2f} | Return: {result.total_return_pct:.2f}% | "
        f"Max Drawdown: {result.max_drawdown_pct:.2f}%"
    )
    if result.benchmark_return_pct is not None and result.alpha_pct is not None:
        print(f"Benchmark Return: {result.benchmark_return_pct:.2f}% | Alpha: {result.alpha_pct:.2f}%")
    else:
        print("Benchmark comparison unavailable for selected date range.")
    print(
        "Risk Analytics: "
        f"Sharpe {_format_metric(result.sharpe_ratio)} | "
        f"Sortino {_format_metric(result.sortino_ratio)} | "
        f"Calmar {_format_metric(result.calmar_ratio)}"
    )
    print(
        "Trade Analytics: "
        f"Win Rate {_format_metric(result.win_rate_pct, suffix='%')} | "
        f"Profit Factor {_format_metric(result.profit_factor)} | "
        f"Avg Trade Return {_format_metric(result.avg_trade_return_pct, suffix='%')}"
    )

    if result.warnings:
        print("Backtest safeguards / approximation notes:")
        for warning in result.warnings:
            print(f"- {warning}")


def handle_backtest_report(conn, args, parser, *, deps: dict[str, Any]) -> None:
    report = deps["backtest_report"](conn, args.run_id)
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
    print(
        "Risk Analytics: "
        f"Sharpe {_format_metric(report.get('sharpe_ratio'))} | "
        f"Sortino {_format_metric(report.get('sortino_ratio'))} | "
        f"Calmar {_format_metric(report.get('calmar_ratio'))}"
    )
    print(
        "Trade Analytics: "
        f"Win Rate {_format_metric(report.get('win_rate_pct'), suffix='%')} | "
        f"Profit Factor {_format_metric(report.get('profit_factor'))} | "
        f"Avg Trade Return {_format_metric(report.get('avg_trade_return_pct'), suffix='%')}"
    )
    if report["warnings"]:
        print(f"Safeguards / notes: {report['warnings']}")


def handle_backtest_leaderboard(conn, args, parser, *, deps: dict[str, Any]) -> None:
    try:
        rows = deps["backtest_leaderboard_entries"](
            conn,
            limit=int(args.limit),
            account_name=args.account,
            strategy=args.strategy,
        )
    except ValueError as error:
        parser.error(str(error))
        return

    if not rows:
        print("No backtest runs matched the selected filters.")
        return

    print(
        "run_id,run_name,account_name,strategy,start_date,end_date,ending_equity,"
        "total_return_pct,max_drawdown_pct,benchmark_return_pct,alpha_pct,"
        "sharpe_ratio,sortino_ratio,calmar_ratio,win_rate_pct,profit_factor,avg_trade_return_pct,"
        "trade_count,created_at"
    )
    for row in rows:
        benchmark_return = row.benchmark_return_pct
        alpha = row.alpha_pct
        benchmark_text = "" if benchmark_return is None else f"{float(benchmark_return):.4f}"
        alpha_text = "" if alpha is None else f"{float(alpha):.4f}"
        sharpe_text = "" if row.sharpe_ratio is None else f"{float(row.sharpe_ratio):.4f}"
        sortino_text = "" if row.sortino_ratio is None else f"{float(row.sortino_ratio):.4f}"
        calmar_text = "" if row.calmar_ratio is None else f"{float(row.calmar_ratio):.4f}"
        win_rate_text = "" if row.win_rate_pct is None else f"{float(row.win_rate_pct):.4f}"
        profit_factor_text = "" if row.profit_factor is None else f"{float(row.profit_factor):.4f}"
        avg_trade_return_text = "" if row.avg_trade_return_pct is None else f"{float(row.avg_trade_return_pct):.4f}"
        run_name = "" if row.run_name is None else str(row.run_name)
        print(
            f"{row.run_id},{run_name},{row.account_name},{row.strategy},"
            f"{row.start_date},{row.end_date},{row.ending_equity:.2f},"
            f"{row.total_return_pct:.4f},{row.max_drawdown_pct:.4f},"
            f"{benchmark_text},{alpha_text},{sharpe_text},{sortino_text},{calmar_text},"
            f"{win_rate_text},{profit_factor_text},{avg_trade_return_text},"
            f"{row.trade_count},{row.created_at}"
        )


def handle_backtest_batch(conn, args, parser, *, deps: dict[str, Any]) -> None:
    account_names = [name.strip() for name in args.accounts.split(",") if name.strip()]
    try:
        results = deps["run_backtest_batch"](
            conn,
            deps["BacktestBatchConfig"](
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
    except ValueError as error:
        parser.error(str(error))
        return

    print("Backtest batch complete.")
    print("rank,account_name,run_id,total_return_pct,max_drawdown_pct,ending_equity,trade_count")
    for rank, result in enumerate(results, start=1):
        print(
            f"{rank},{result.account_name},{result.run_id},{result.total_return_pct:.4f},"
            f"{result.max_drawdown_pct:.4f},{result.ending_equity:.2f},{result.trade_count}"
        )


def handle_backtest_walk_forward(conn, args, parser, *, deps: dict[str, Any]) -> None:
    try:
        summary = deps["run_walk_forward_backtest"](
            conn,
            deps["WalkForwardConfig"](
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
    except ValueError as error:
        parser.error(str(error))
        return

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


def handle_backtest_optimize(conn, args, parser, *, deps: dict[str, Any]) -> None:
    try:
        search_space = json.loads(args.search_space)
    except json.JSONDecodeError as error:
        parser.error(f"--search-space must be valid JSON: {error}")
        return
    if not isinstance(search_space, dict):
        parser.error("--search-space must be a JSON object mapping parameter -> list of values")
        return

    try:
        summary = deps["run_walk_forward_optimization"](
            conn,
            deps["OptimizerConfig"](
                account_name=args.account,
                tickers_file=args.tickers_file,
                universe_history_dir=args.universe_history_dir,
                strategy=args.strategy,
                search_space=search_space,
                start=args.start,
                end=args.end,
                lookback_months=args.lookback_months,
                slippage_bps=args.slippage_bps,
                fee_per_trade=args.fee,
                allow_approximate_leaps=bool(args.allow_approximate_leaps),
                train_months=args.train_months,
                test_months=args.test_months,
                step_months=args.step_months,
                holdout_months=args.holdout_months,
                candidate_budget=args.candidate_budget,
                warmup_months=args.warmup_months,
            ),
            run_metrics_only_fn=deps["run_backtest_metrics_only"],
            run_persisted_fn=deps["run_backtest"],
        )
    except ValueError as error:
        parser.error(str(error))
        return

    _print_optimization_summary(summary)


def _print_optimization_summary(summary: Any) -> None:
    print(
        f"Walk-forward optimization: account={summary.account_name} strategy={summary.strategy} "
        f"objective={summary.objective_name}"
    )
    print(f"Default params: {summary.default_params}")
    print(f"Windows: {len(summary.windows)}")
    for window in summary.windows:
        print(
            f"  W{window.window_index:02d} test {window.split.test_start}..{window.split.test_end} "
            f"winner={window.winner.params} "
            f"OOS winner={_format_metric(window.winner_oos.total_return_pct, suffix='%')} "
            f"vs default={_format_metric(window.baseline_oos.total_return_pct, suffix='%')} "
            f"(run {window.winner_oos.run_id})"
        )
    if summary.windows:
        window_count = len(summary.windows)
        avg_winner = sum(w.winner_oos.total_return_pct for w in summary.windows) / window_count
        avg_default = sum(w.baseline_oos.total_return_pct for w in summary.windows) / window_count
        beats = sum(1 for w in summary.windows if w.winner_oos.total_return_pct > w.baseline_oos.total_return_pct)
        print(
            f"OOS mean total return: winner={avg_winner:.2f}% vs default={avg_default:.2f}% "
            f"| winner beat default in {beats}/{window_count} windows"
        )
    if summary.holdout is None:
        print("Holdout: disabled")
    else:
        holdout = summary.holdout
        print(
            f"Holdout {holdout.holdout_start}..{holdout.holdout_end} params={holdout.winner_params} "
            f"winner={_format_metric(holdout.winner.total_return_pct, suffix='%')} "
            f"vs default={_format_metric(holdout.baseline.total_return_pct, suffix='%')} "
            f"(run {holdout.winner.run_id})"
        )


def handle_backtest_walk_forward_report(
    conn,
    args,
    parser,
    *,
    deps: dict[str, Any],
) -> None:
    try:
        report = deps["walk_forward_report"](
            conn,
            group_id=args.group_id,
            account_name=args.account,
            strategy_name=args.strategy,
        )
    except ValueError as error:
        parser.error(str(error))
        return

    print(
        f"Walk-forward Group {report['group_id']} | account={report['account_name']} "
        f"strategy={report['strategy_name']}"
    )
    print(
        f"Range: {report['start_date']}..{report['end_date']} | Created: {report['created_at']} "
        f"| Windows: {report['window_count']} | Prefix: {report['run_name_prefix'] or 'n/a'}"
    )
    print(
        f"Average Return: {report['average_return_pct']:.2f}% | Median Return: {report['median_return_pct']:.2f}% "
        f"| Best: {report['best_return_pct']:.2f}% | Worst: {report['worst_return_pct']:.2f}%"
    )
    print("window,range,run_id,run_name,return_pct,max_drawdown_pct,trade_count")
    for window in report["windows"]:
        summary = window["backtest_summary"]
        print(
            f"{window['window_index']},{window['window_start']}..{window['window_end']},"
            f"{summary['run_id']},{summary['run_name'] or ''},{window['total_return_pct']:.4f},"
            f"{summary['max_drawdown_pct']:.4f},{summary['trade_count']}"
        )
