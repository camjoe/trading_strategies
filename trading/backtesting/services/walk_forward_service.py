from __future__ import annotations

from statistics import median

from trading.backtesting.models import BacktestConfig, WalkForwardSummary


def execute_walk_forward_backtest(
    conn,
    *,
    cfg,
    start_date,
    end_date,
    windows: list[tuple],
    run_backtest_fn,
) -> WalkForwardSummary:
    if not windows:
        raise ValueError("No walk-forward windows generated for the selected date range.")

    run_ids: list[int] = []
    total_returns: list[float] = []

    for i, (window_start, window_end) in enumerate(windows):
        prefix = cfg.run_name_prefix.strip() if cfg.run_name_prefix else ""
        run_name = f"wf_{prefix}_{i + 1:02d}" if prefix else f"wf_{i + 1:02d}"

        test_cfg = BacktestConfig(
            account_name=cfg.account_name,
            tickers_file=cfg.tickers_file,
            universe_history_dir=cfg.universe_history_dir,
            start=window_start.isoformat(),
            end=window_end.isoformat(),
            lookback_months=None,
            slippage_bps=cfg.slippage_bps,
            fee_per_trade=cfg.fee_per_trade,
            run_name=run_name,
            allow_approximate_leaps=cfg.allow_approximate_leaps,
        )

        result = run_backtest_fn(conn, test_cfg)
        run_ids.append(result.run_id)
        total_returns.append(result.total_return_pct)

    if not total_returns:
        raise ValueError("No returns were computed.")

    return WalkForwardSummary(
        account_name=cfg.account_name,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        window_count=len(windows),
        run_ids=run_ids,
        average_return_pct=sum(total_returns) / len(total_returns),
        median_return_pct=float(median(total_returns)),
        best_return_pct=max(total_returns),
        worst_return_pct=min(total_returns),
    )
