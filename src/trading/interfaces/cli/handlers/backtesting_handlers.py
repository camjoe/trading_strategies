from __future__ import annotations

import json
from collections import Counter
from typing import Any


def _format_metric(value: float | None, *, suffix: str = "") -> str:
    return "n/a" if value is None else f"{value:.2f}{suffix}"


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
    report = deps["backtest_report_full"](conn, args.run_id)
    summary = report.summary
    print(
        f"Backtest Run {summary.run_id} ({summary.run_name or 'unnamed'}) | "
        f"account={summary.account_name} strategy={summary.strategy}"
    )
    print(
        f"Range: {summary.start_date}..{summary.end_date} | Created: {summary.created_at} "
        f"| Trades: {summary.trade_count}"
    )
    print(
        f"Start Equity: {summary.starting_equity:.2f} | End Equity: {summary.ending_equity:.2f} "
        f"| Return: {summary.total_return_pct:.2f}% | Max DD: {summary.max_drawdown_pct:.2f}%"
    )
    print(
        f"Slippage (bps): {summary.slippage_bps:.2f} | Fee/Trade: {summary.fee_per_trade:.2f} "
        f"| Tickers File: {summary.tickers_file}"
    )
    print(
        "Risk Analytics: "
        f"Sharpe {_format_metric(summary.sharpe_ratio)} | "
        f"Sortino {_format_metric(summary.sortino_ratio)} | "
        f"Calmar {_format_metric(summary.calmar_ratio)}"
    )
    print(
        "Trade Analytics: "
        f"Win Rate {_format_metric(summary.win_rate_pct, suffix='%')} | "
        f"Profit Factor {_format_metric(summary.profit_factor)} | "
        f"Avg Trade Return {_format_metric(summary.avg_trade_return_pct, suffix='%')}"
    )
    if summary.warnings:
        print(f"Safeguards / notes: {' | '.join(summary.warnings)}")


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
    if summary.experiment_id is not None:
        print(f"Persisted optimization experiment #{summary.experiment_id}")
        print(f"Promote its winner with: backtest-optimize-promote {summary.experiment_id} --key <new_key>")


def handle_backtest_optimize_show(conn, args, parser, *, deps: dict[str, Any]) -> None:
    experiment = deps["fetch_optimization_experiment"](conn, experiment_id=args.experiment_id)
    if experiment is None:
        parser.error(f"Optimization experiment not found: {args.experiment_id}")
        return
    _print_experiment(experiment, evaluate_promotion_gate=deps["evaluate_promotion_gate"])
    if experiment.status == "failed":
        return
    windows = deps["fetch_optimization_windows"](conn, experiment_id=args.experiment_id)
    trials = deps["fetch_optimization_trials"](conn, experiment_id=args.experiment_id)
    _print_window_audit(windows, trials)
    compounded = deps["fetch_compounded_oos"](conn, experiment_id=args.experiment_id)
    _print_compounded_oos(compounded)
    manifest = deps["fetch_optimization_manifest"](conn, experiment_id=args.experiment_id)
    _print_manifest(manifest)


def handle_backtest_optimize_promote(conn, args, parser, *, deps: dict[str, Any]) -> None:
    try:
        variant = deps["promote_optimization_experiment"](
            conn,
            experiment_id=args.experiment_id,
            new_strategy_key=args.key,
            freeze=not args.no_freeze,
            allow_no_edge=args.allow_no_edge,
        )
    except ValueError as error:
        parser.error(str(error))
        return
    print(
        f"Promoted experiment #{args.experiment_id} -> strategy {variant.strategy_key} "
        f"(primitive={variant.primitive} status={variant.status} params={variant.params_json})"
    )


def _print_experiment(experiment: Any, *, evaluate_promotion_gate: Any) -> None:
    print(
        f"Optimization experiment #{experiment.id} | account_id={experiment.account_id} "
        f"primitive={experiment.primitive} objective={experiment.objective_name} created={experiment.created_at} "
        f"status={experiment.status}"
    )
    if experiment.status == "failed":
        print(
            f"Failed during {experiment.failure_stage} after {experiment.window_count} window(s): "
            f"{experiment.failure_message}"
        )
        return
    print(
        f"Range {experiment.start_date}..{experiment.end_date} | windows={experiment.window_count} "
        f"| train/test/step/holdout(mo)={experiment.train_months}/{experiment.test_months}/"
        f"{experiment.step_months}/{experiment.holdout_months} warmup={experiment.warmup_months}"
    )
    print(f"Search space: {experiment.search_space_json} (budget {experiment.candidate_budget})")
    print(f"Winner params: {experiment.winner_params_json}")
    if experiment.oos_mean_winner_return_pct is not None:
        print(
            f"OOS means: return {_pair(experiment.oos_mean_winner_return_pct, experiment.oos_mean_baseline_return_pct)} "
            f"| winner beat default in {experiment.oos_windows_beat_baseline}/{experiment.window_count} windows"
        )
    if experiment.holdout_run_id is None:
        print("Holdout: none")
    else:
        print(
            f"Holdout (run {experiment.holdout_run_id}): "
            f"return {_pair(experiment.holdout_winner_return_pct, experiment.holdout_baseline_return_pct)}"
        )
    gate = evaluate_promotion_gate(
        oos_mean_winner_return_pct=experiment.oos_mean_winner_return_pct,
        oos_mean_baseline_return_pct=experiment.oos_mean_baseline_return_pct,
        oos_windows_beat_baseline=experiment.oos_windows_beat_baseline,
        window_count=experiment.window_count,
        holdout_winner_return_pct=experiment.holdout_winner_return_pct,
        holdout_baseline_return_pct=experiment.holdout_baseline_return_pct,
    )
    if gate.passed:
        print("Promotion gate: PASS")
    else:
        print(f"Promotion gate: FAIL ({'; '.join(gate.reasons)})")
    if experiment.promoted_strategy_id is None:
        print("Promotion: not promoted")
    else:
        print(f"Promotion: strategy id {experiment.promoted_strategy_id}")


def _print_window_audit(windows: list[Any], trials: list[Any]) -> None:
    """Print the persisted per-window / per-candidate audit trail.

    The multiple-testing record: every window's train/test boundaries plus each
    evaluated candidate's objective and eligibility — not just the winner."""
    if not windows:
        print("Windows: none persisted (experiment predates per-window audit)")
        return
    trials_by_window: dict[int, list[Any]] = {}
    for trial in trials:
        trials_by_window.setdefault(trial.window_id, []).append(trial)
    print(f"Windows ({len(windows)}) with per-candidate trials:")
    for window in windows:
        window_trials = trials_by_window.get(window.id, [])
        eligible = sum(1 for trial in window_trials if trial.eligible)
        winner = next((trial for trial in window_trials if trial.selected), None)
        winner_label = (
            f"win #{winner.candidate_index} score {_format_metric(winner.objective_value, suffix='')}"
            if winner is not None
            else "no winner recorded"
        )
        print(
            f"  W{window.window_index:02d} train {window.train_start}..{window.train_end} "
            f"test {window.test_start}..{window.test_end} (oos run {window.oos_run_id}) | "
            f"{len(window_trials)} candidates, {eligible} eligible | {winner_label}"
        )
        for reason, count in _rejection_tally(window_trials):
            print(f"       rejected: {reason} x{count}")


def _print_manifest(manifest: Any) -> None:
    """Print the frozen provenance manifest: the assumptions the run executed under."""
    if manifest is None:
        print("Provenance: unavailable (experiment predates run manifests)")
        return
    print(f"Provenance ({manifest.manifest_version}) | account={manifest.account_name} book_id={manifest.book_id}")
    print(
        f"  economics: initial_cash={manifest.initial_cash:.2f} benchmark={manifest.benchmark_ticker} "
        f"slippage_bps={manifest.slippage_bps:.2f} fee={manifest.fee_per_trade:.2f}"
    )
    print(f"  execution: {manifest.effective_execution_json}")
    lineage = manifest.universe_history_dir or manifest.tickers_file or "n/a"
    print(f"  universe: {manifest.universe_size} tickers | lineage={lineage}")
    revision = manifest.engine_revision or "unknown"
    print(f"  data: provider={manifest.market_data_provider} as_of={manifest.data_as_of} | engine={revision}")


def _print_compounded_oos(series: Any) -> None:
    """Print the compounded chronological OOS series across the experiment's windows.

    Each OOS window is an independently reset account, so returns are compounded
    (geometrically linked), never summed; a window with a preceding time gap is marked."""
    if series is None or not series.points:
        print("Compounded OOS: unavailable (no persisted windows or missing OOS equity)")
        return
    gap_count = sum(1 for point in series.points if point.gap_before)
    gap_note = f", {gap_count} gap(s)" if series.has_gaps else ""
    print(f"Compounded OOS (across {len(series.points)} windows{gap_note}): {series.compounded_return_pct:.2f}%")
    for point in series.points:
        marker = " [GAP]" if point.gap_before else ""
        print(
            f"  W{point.window_index:02d} {point.test_start}..{point.test_end}{marker} "
            f"period {point.period_return_pct:.2f}% | cumulative {point.cumulative_return_pct:.2f}%"
        )


def _rejection_tally(window_trials: list[Any]) -> list[tuple[str, int]]:
    """Count ineligible candidates by rejection-reason family (prefix before any detail)."""
    tally = Counter(
        (trial.rejection_reason or "unknown").split(" (")[0] for trial in window_trials if not trial.eligible
    )
    return sorted(tally.items())


def _pair(winner: float | None, default: float | None, *, suffix: str = "%") -> str:
    """Format a winner/default metric pair for the optimizer summary."""
    return f"{_format_metric(winner, suffix=suffix)}/{_format_metric(default, suffix=suffix)}"


def _print_optimization_summary(summary: Any) -> None:
    print(
        f"Walk-forward optimization: account={summary.account_name} strategy={summary.strategy} "
        f"objective={summary.objective_name}"
    )
    print(f"Default params: {summary.default_params}")
    print(f"Windows: {len(summary.windows)} (metrics shown as winner/default)")
    for window in summary.windows:
        winner, default = window.winner_oos, window.baseline_oos
        print(
            f"  W{window.window_index:02d} {window.split.test_start}..{window.split.test_end} "
            f"win={window.winner.params} | "
            f"return {_pair(winner.total_return_pct, default.total_return_pct)} | "
            f"maxDD {_pair(winner.max_drawdown_pct, default.max_drawdown_pct)} (run {winner.run_id})"
        )
    if summary.windows:
        count = len(summary.windows)
        avg_win_return = sum(w.winner_oos.total_return_pct for w in summary.windows) / count
        avg_def_return = sum(w.baseline_oos.total_return_pct for w in summary.windows) / count
        avg_win_dd = sum(w.winner_oos.max_drawdown_pct for w in summary.windows) / count
        avg_def_dd = sum(w.baseline_oos.max_drawdown_pct for w in summary.windows) / count
        beats = sum(1 for w in summary.windows if w.winner_oos.total_return_pct > w.baseline_oos.total_return_pct)
        print(
            f"OOS means: return {_pair(avg_win_return, avg_def_return)} | maxDD {_pair(avg_win_dd, avg_def_dd)} "
            f"| winner beat default on return in {beats}/{count} windows"
        )
    if summary.holdout is None:
        print("Holdout: disabled")
    else:
        holdout = summary.holdout
        winner, default = holdout.winner, holdout.baseline
        print(
            f"Holdout {holdout.holdout_start}..{holdout.holdout_end} params={holdout.winner_params} (run {winner.run_id})"
        )
        print(
            f"  return {_pair(winner.total_return_pct, default.total_return_pct)} | "
            f"maxDD {_pair(winner.max_drawdown_pct, default.max_drawdown_pct)} | "
            f"annualized {_pair(winner.annualized_return_pct, default.annualized_return_pct)} | "
            f"calmar {_pair(winner.calmar_ratio, default.calmar_ratio, suffix='')}"
        )
