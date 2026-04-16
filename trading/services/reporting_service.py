from __future__ import annotations

import sqlite3
from datetime import date
from typing import Callable

from common.market_data import get_provider
from common.time import utc_now_iso
from trading.domain.evaluation_models import StrategyEvaluationArtifact
from trading.utils.coercion import row_expect_float, row_expect_int, row_expect_str, row_float
from trading.domain.accounting import compute_account_state
from trading.models import AccountState
from trading.repositories import (
    fetch_account_listing_rows,
    fetch_recent_equity_rows,
    fetch_snapshot_history_rows,
    insert_snapshot_row,
)
from trading.services.accounts_service import (
    GOAL_NOT_SET_TEXT,
    format_account_policy_text,
    format_goal_text,
    get_account,
)
from trading.services.accounting_service import load_trades
from trading.services.evaluation_service import fetch_strategy_evaluation_for_account_row
from trading.services.pricing_service import benchmark_stats as _benchmark_stats_svc
from trading.services.pricing_service import fetch_latest_prices as _fetch_prices_svc

# ---------------------------------------------------------------------------
# Module-level adapters (provider injection)
# ---------------------------------------------------------------------------

# Compare output shows at most this many individual positions before truncating.
POSITION_SUMMARY_LIMIT = 5

# Trend inference needs at least two persisted points plus the current equity value.
MIN_TREND_HISTORY_POINTS = 3

# Trend inference always loads at least this many persisted rows to make a direction call.
MIN_TREND_LOOKBACK_ROWS = 2

# Equity moves inside this band are treated as flat for operator-facing trend summaries.
TREND_FLAT_BAND_PCT = 1.0

def fetch_latest_prices(tickers: list[str]) -> dict[str, float]:
    """Module-level adapter: inject provider and delegate to pricing_service."""
    return _fetch_prices_svc(tickers, fetch_close_series_fn=get_provider().fetch_close_series)


def benchmark_stats(
    benchmark_ticker: str, initial_cash: float, created_at: str
) -> tuple[float | None, float | None]:
    """Module-level adapter: inject provider and delegate to pricing_service."""
    return _benchmark_stats_svc(
        benchmark_ticker, initial_cash, created_at,
        fetch_close_history_fn=get_provider().fetch_close_history,
        today_fn=date.today,
    )


# ---------------------------------------------------------------------------
# Pure computation helpers
# ---------------------------------------------------------------------------

def compute_market_value_and_unrealized(
    positions: dict[str, float],
    avg_cost: dict[str, float],
    prices: dict[str, float],
) -> tuple[float, float]:
    market_value = 0.0
    unrealized = 0.0
    for ticker, qty in positions.items():
        price = prices.get(ticker)
        if price is None:
            continue
        market_value += qty * price
        unrealized += (price - avg_cost.get(ticker, 0.0)) * qty
    return market_value, unrealized


def strategy_return_pct(equity: float, initial_cash: float) -> float:
    if not initial_cash:
        raise ValueError(f"Cannot compute return %: initial_cash is 0 (equity={equity:.2f})")
    return ((equity / initial_cash) - 1.0) * 100.0


def benchmark_available(benchmark_equity: float | None, benchmark_return_pct: float | None) -> bool:
    return benchmark_equity is not None and benchmark_return_pct is not None


def alpha_pct(strategy_return_pct_value: float, benchmark_return_pct_value: float) -> float:
    return strategy_return_pct_value - benchmark_return_pct_value


def positions_summary_text(positions: dict[str, float]) -> tuple[int, str]:
    position_count = len(positions)
    if not positions:
        return position_count, "none"
    sorted_positions = sorted(positions.items(), key=lambda x: x[0])
    positions_text = ", ".join(
        f"{ticker}:{qty:.2f}"
        for ticker, qty in sorted_positions[:POSITION_SUMMARY_LIMIT]
    )
    if len(sorted_positions) > POSITION_SUMMARY_LIMIT:
        positions_text += ", ..."
    return position_count, positions_text


# ---------------------------------------------------------------------------
# Low-level stats builder (injected deps — for testing / composability)
# ---------------------------------------------------------------------------

def _build_account_stats_impl(
    conn: sqlite3.Connection,
    account: dict[str, object],
    *,
    load_trades_fn: Callable[[sqlite3.Connection, int], list[dict[str, object]]],
    compute_account_state_fn: Callable[[float, list[dict[str, object]]], AccountState],
    fetch_latest_prices_fn: Callable[[list[str]], dict[str, float]],
    row_expect_int_fn: Callable[[dict[str, object], str], int],
    row_expect_float_fn: Callable[[dict[str, object], str], float],
) -> tuple[AccountState, dict[str, float], float, float, float]:
    account_id = row_expect_int_fn(account, "id")
    initial_cash = row_expect_float_fn(account, "initial_cash")
    trades = load_trades_fn(conn, account_id)
    state = compute_account_state_fn(initial_cash, trades)
    tickers = sorted(state.positions.keys())
    prices = fetch_latest_prices_fn(tickers) if tickers else {}
    market_value, unrealized = compute_market_value_and_unrealized(state.positions, state.avg_cost, prices)
    equity = state.cash + market_value
    return state, prices, market_value, unrealized, equity


def _infer_overall_trend_impl(
    conn: sqlite3.Connection,
    account_id: int,
    current_equity: float,
    lookback: int,
    *,
    fetch_recent_equity_rows_fn: Callable[..., list[dict[str, object]]],
    row_float_fn: Callable[..., float | None],
) -> str:
    rows = fetch_recent_equity_rows_fn(
        conn,
        account_id=account_id,
        limit=int(max(lookback, MIN_TREND_LOOKBACK_ROWS)),
    )
    history: list[float] = [h for h in (row_float_fn(r, "equity") for r in rows) if h is not None]
    history.reverse()
    history.append(current_equity)

    if len(history) < MIN_TREND_HISTORY_POINTS:
        return "insufficient-data"

    first = history[0]
    last = history[-1]
    if first == 0:
        return "insufficient-data"

    move_pct = ((last - first) / first) * 100.0
    if move_pct > TREND_FLAT_BAND_PCT:
        return "up"
    if move_pct < -TREND_FLAT_BAND_PCT:
        return "down"
    return "flat"


# ---------------------------------------------------------------------------
# Public stats API (deps bound at call time)
# ---------------------------------------------------------------------------

def build_account_stats(
    conn: sqlite3.Connection,
    account: dict[str, object],
) -> tuple[AccountState, dict[str, float], float, float, float]:
    return _build_account_stats_impl(
        conn,
        account,
        load_trades_fn=load_trades,
        compute_account_state_fn=compute_account_state,
        fetch_latest_prices_fn=fetch_latest_prices,
        row_expect_int_fn=row_expect_int,
        row_expect_float_fn=row_expect_float,
    )


def infer_overall_trend(
    conn: sqlite3.Connection,
    account_id: int,
    current_equity: float,
    lookback: int,
    *,
    fetch_recent_equity_rows_fn: Callable[..., list[dict[str, object]]] | None = None,
    row_float_fn: Callable[..., float | None] | None = None,
) -> str:
    return _infer_overall_trend_impl(
        conn,
        account_id,
        current_equity,
        lookback,
        fetch_recent_equity_rows_fn=fetch_recent_equity_rows_fn or fetch_recent_equity_rows,
        row_float_fn=row_float_fn or row_float,
    )


# ---------------------------------------------------------------------------
# Display helpers (private)
# ---------------------------------------------------------------------------

def _print_leaps_params(account: dict[str, object]) -> None:
    print(
        "LEAPs Parameters: "
        f"strike_offset_pct={account['option_strike_offset_pct']} "
        f"min_dte={account['option_min_dte']} max_dte={account['option_max_dte']}"
    )
    print(
        "LEAPs Options Filters: "
        f"type={account['option_type']} "
        f"delta={account['target_delta_min']}-{account['target_delta_max']} "
        f"iv_rank={account['iv_rank_min']}-{account['iv_rank_max']}"
    )
    print(
        "LEAPs/Options Risk Limits: "
        f"max_premium={account['max_premium_per_trade']} "
        f"max_contracts={account['max_contracts_per_trade']} "
        f"roll_dte={account['roll_dte_threshold']} "
        f"leaps_profit_take_pct={account['profit_take_pct']} "
        f"leaps_max_loss_pct={account['max_loss_pct']}"
    )


def _print_account_header(account: dict[str, object]) -> None:
    print(f"Account: {account['name']}")
    print(f"Display Name: {account['descriptive_name']}")
    print(f"Account Policy: {format_account_policy_text(account)}")
    goal_text = format_goal_text(account)
    if goal_text != GOAL_NOT_SET_TEXT:
        print(f"Goal Metadata: {goal_text}")
    if account["instrument_mode"] == "leaps":
        _print_leaps_params(account)


def _print_performance_lines(
    account: dict[str, object],
    cash: float,
    market_value: float,
    equity: float,
    realized_pnl: float,
    unrealized: float,
    strategy_return_pct_value: float,
    benchmark_equity: float | None,
    benchmark_return_pct: float | None,
) -> None:
    initial_cash = row_float(account, "initial_cash")
    print(f"Initial Cash: {initial_cash:.2f}" if initial_cash is not None else "Initial Cash: N/A")
    print(f"Cash: {cash:.2f}")
    print(f"Market Value: {market_value:.2f}")
    print(f"Equity: {equity:.2f}")
    print(f"Account Return %: {strategy_return_pct_value:.2f}")
    print(f"Realized PnL: {realized_pnl:.2f}")
    print(f"Unrealized PnL: {unrealized:.2f}")

    if benchmark_available(benchmark_equity, benchmark_return_pct):
        assert benchmark_return_pct is not None
        assert benchmark_equity is not None
        alpha_value = alpha_pct(strategy_return_pct_value, benchmark_return_pct)
        print(f"Benchmark Equity: {benchmark_equity:.2f}")
        print(f"Benchmark Return %: {benchmark_return_pct:.2f}")
        print(f"Account Alpha vs Benchmark %: {alpha_value:.2f}")
        return

    print("Benchmark comparison: unavailable (price history not found)")


def _print_open_positions(
    positions: dict[str, float],
    avg_cost: dict[str, float],
    prices: dict[str, float],
) -> None:
    if not positions:
        print("Open Positions: none")
        return

    print("Open Positions:")
    for ticker in sorted(positions.keys()):
        qty = positions[ticker]
        avg = avg_cost.get(ticker, 0.0)
        px = prices.get(ticker)
        px_display = f"{px:.2f}" if px is not None else "N/A"
        print(f"- {ticker}: qty={qty:.4f}, avg_cost={avg:.2f}, last_price={px_display}")


def _compare_account_header(account: dict[str, object]) -> str:
    return f"- {account['name']} | display_name={account['descriptive_name']}"


def _compare_goal_metadata_line(account: dict[str, object]) -> str | None:
    goal_text = format_goal_text(account)
    if goal_text == GOAL_NOT_SET_TEXT:
        return None
    return f"  goal_metadata={goal_text}"


def _compare_benchmark_line(
    strategy_return_pct_value: float,
    benchmark_equity: float | None,
    benchmark_return_pct: float | None,
) -> str:
    if benchmark_available(benchmark_equity, benchmark_return_pct):
        assert benchmark_equity is not None
        assert benchmark_return_pct is not None
        alpha_value = alpha_pct(strategy_return_pct_value, benchmark_return_pct)
        return (
            f"  benchmark_equity={benchmark_equity:.2f} benchmark_return={benchmark_return_pct:.2f}% "
            f"account_alpha={alpha_value:.2f}%"
        )
    return "  benchmark_equity=N/A benchmark_return=N/A account_alpha=N/A"


def _format_percentage_or_na(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}%"


def _format_backtest_evidence_summary(evaluation: StrategyEvaluationArtifact) -> str:
    if not evaluation.backtest.available:
        return "backtest=N/A"
    return (
        f"backtest={_format_percentage_or_na(evaluation.backtest.total_return_pct)} "
        f"({evaluation.backtest.trade_count or 0} trades)"
    )


def _format_paper_live_evidence_summary(evaluation: StrategyEvaluationArtifact) -> str:
    label = evaluation.paper_live.mode or "paper_live"
    if not evaluation.paper_live.available:
        return f"{label}=N/A"
    return (
        f"{label}={_format_percentage_or_na(evaluation.paper_live.return_pct)} "
        f"({evaluation.paper_live.snapshot_count or 0} snapshots)"
    )


def _evaluation_summary_line(
    evaluation: StrategyEvaluationArtifact,
    *,
    prefix: str,
) -> str:
    return (
        f"{prefix}{_format_backtest_evidence_summary(evaluation)} | "
        f"{_format_paper_live_evidence_summary(evaluation)} | "
        f"blended_score={_format_percentage_or_na(evaluation.confidence.blended_score)} | "
        f"confidence={evaluation.confidence.overall_confidence:.2f}"
    )


# ---------------------------------------------------------------------------
# Orchestration (account report / compare / snapshot)
# ---------------------------------------------------------------------------

def account_report(conn: sqlite3.Connection, account_name: str) -> tuple[dict[str, float], dict[str, float]]:
    account = get_account(conn, account_name)
    state, prices, market_value, unrealized, equity = build_account_stats(conn, account)
    evaluation = fetch_strategy_evaluation_for_account_row(conn, account)
    benchmark_ticker = row_expect_str(account, "benchmark_ticker")
    initial_cash = row_expect_float(account, "initial_cash")
    created_at = row_expect_str(account, "created_at")
    effective_initial = initial_cash if initial_cash else state.total_deposited
    benchmark_equity, benchmark_return_pct = benchmark_stats(
        benchmark_ticker, effective_initial, created_at
    )
    strategy_return_pct_value = strategy_return_pct(equity, effective_initial) if effective_initial else 0.0

    _print_account_header(account)
    _print_performance_lines(
        account,
        state.cash,
        market_value,
        equity,
        state.realized_pnl,
        unrealized,
        strategy_return_pct_value,
        benchmark_equity,
        benchmark_return_pct,
    )
    print(_evaluation_summary_line(evaluation, prefix="Evaluation Summary: "))
    _print_open_positions(state.positions, state.avg_cost, prices)

    stats = {
        "cash": state.cash,
        "market_value": market_value,
        "equity": equity,
        "realized_pnl": state.realized_pnl,
        "unrealized_pnl": unrealized,
        "strategy_return_pct": strategy_return_pct_value,
    }
    return stats, state.positions


def compare_strategies(conn: sqlite3.Connection, lookback: int) -> None:
    accounts = fetch_account_listing_rows(conn)

    if not accounts:
        print("No paper accounts found.")
        return

    print("Account policy comparison (current paper account state):")
    print(
        "Compares each account's current policy and holdings state, with canonical evaluation evidence "
        "summaries when available."
    )
    for account in accounts:
        state, _prices, _market_value, _unrealized, equity = build_account_stats(conn, account)
        evaluation = fetch_strategy_evaluation_for_account_row(conn, account)
        initial_cash = row_expect_float(account, "initial_cash")
        if not initial_cash:
            continue
        benchmark_ticker = row_expect_str(account, "benchmark_ticker")
        created_at = row_expect_str(account, "created_at")
        account_id = row_expect_int(account, "id")
        strategy_return_pct_value = strategy_return_pct(equity, initial_cash)
        bench_equity, bench_return_pct = benchmark_stats(
            benchmark_ticker, initial_cash, created_at
        )
        trend = infer_overall_trend(conn, account_id, equity, lookback)

        position_count, positions_text = positions_summary_text(state.positions)

        print(_compare_account_header(account))
        print(f"  account_policy={format_account_policy_text(account)}")
        goal_metadata_line = _compare_goal_metadata_line(account)
        if goal_metadata_line is not None:
            print(goal_metadata_line)
        print(
            f"  equity={equity:.2f} account_return={strategy_return_pct_value:.2f}% "
            f"positions={position_count} trend={trend}"
        )
        print(_compare_benchmark_line(strategy_return_pct_value, bench_equity, bench_return_pct))
        print(_evaluation_summary_line(evaluation, prefix="  "))
        print(f"  positions: {positions_text}")


def snapshot_account(conn: sqlite3.Connection, account_name: str, snapshot_time: str | None) -> None:
    account = get_account(conn, account_name)
    stats, _ = account_report(conn, account_name)
    insert_snapshot_row(
        conn,
        account_id=account["id"],
        snapshot_time=snapshot_time or utc_now_iso(),
        cash=stats["cash"],
        market_value=stats["market_value"],
        equity=stats["equity"],
        realized_pnl=stats["realized_pnl"],
        unrealized_pnl=stats["unrealized_pnl"],
    )
    print("Snapshot saved.")


def show_snapshots(conn: sqlite3.Connection, account_name: str, limit: int) -> None:
    account = get_account(conn, account_name)
    rows = fetch_snapshot_history_rows(
        conn,
        account_id=account["id"],
        limit=int(limit),
    )

    if not rows:
        print("No snapshots found.")
        return

    print(f"Snapshot history (latest {limit}) for {account_name}:")
    for r in rows:
        print(
            f"- {r['snapshot_time']} | equity={r['equity']:.2f} cash={r['cash']:.2f} "
            f"mv={r['market_value']:.2f} realized={r['realized_pnl']:.2f} "
            f"unrealized={r['unrealized_pnl']:.2f}"
        )


# ---------------------------------------------------------------------------
# Backward-compat wrappers (kept for any callers that imported these)
# ---------------------------------------------------------------------------

def load_account_trades(conn: sqlite3.Connection, account_id: int) -> list:
    return load_trades(conn, account_id)


def take_account_snapshot(conn: sqlite3.Connection, account_name: str, *, snapshot_time: str | None = None) -> None:
    snapshot_account(conn, account_name, snapshot_time=snapshot_time)


def get_account_stats(conn: sqlite3.Connection, row: dict[str, object]) -> tuple:
    return build_account_stats(conn, row)
