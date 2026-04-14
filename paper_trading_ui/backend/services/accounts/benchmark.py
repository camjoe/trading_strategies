from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import date

import pandas as pd

from common.coercion import coerce_float
from common.market_data import get_provider


def _snapshot_time(snapshot: sqlite3.Row | dict[str, object]) -> str:
    if hasattr(snapshot, "keys") and "time" in snapshot.keys():
        return str(snapshot["time"])
    return str(snapshot["snapshot_time"])


def _snapshot_equity(snapshot: sqlite3.Row | dict[str, object]) -> float:
    value = coerce_float(snapshot["equity"])
    if value is None:
        raise ValueError("Snapshot equity is required for benchmark overlay.")
    return value


def fetch_benchmark_close_history(
    benchmark_ticker: str,
    *,
    start_date: date,
    end_date: date,
) -> pd.Series | None:
    ticker = benchmark_ticker.strip().upper()
    if not ticker:
        return None
    close_history = get_provider().fetch_close_history([ticker], start_date, end_date)
    if close_history is None:
        return None
    try:
        close_col = close_history[ticker]
    except Exception:
        return None
    if isinstance(close_col, pd.DataFrame):
        if close_col.shape[1] == 0:
            return None
        return close_col.iloc[:, 0].dropna()
    return close_col.dropna()


def _normalize_close_history(close_history: pd.Series) -> pd.Series:
    normalized = close_history.copy()
    normalized.index = pd.to_datetime(normalized.index, utc=True).tz_convert(None).normalize()
    return normalized[~normalized.index.duplicated(keep="last")].sort_index()


def _close_price_on_or_before(close_history: pd.Series, snapshot_time: str) -> float | None:
    as_of = pd.Timestamp(snapshot_time).tz_localize(None).normalize()
    matches = close_history.loc[:as_of]
    if matches.empty:
        return None
    return float(matches.iloc[-1])


def build_live_benchmark_overlay(
    summary: dict[str, object],
    snapshots: Sequence[sqlite3.Row | dict[str, object]],
) -> dict[str, object] | None:
    if len(snapshots) < 2:
        return None

    ordered_snapshots = sorted(list(snapshots), key=_snapshot_time)
    starting_equity = _snapshot_equity(ordered_snapshots[0])
    if starting_equity <= 0:
        return None

    benchmark_ticker = str(summary.get("benchmark") or "").strip().upper()
    if not benchmark_ticker:
        return None

    start_date = date.fromisoformat(_snapshot_time(ordered_snapshots[0])[:10])
    end_date = date.fromisoformat(_snapshot_time(ordered_snapshots[-1])[:10])
    try:
        close_history = fetch_benchmark_close_history(
            benchmark_ticker,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception:
        return None
    if close_history is None or close_history.empty:
        return None

    normalized_close = _normalize_close_history(close_history)
    if normalized_close.empty:
        return None
    start_price = _close_price_on_or_before(normalized_close, _snapshot_time(ordered_snapshots[0]))
    if start_price is None or start_price <= 0:
        return None

    points: list[dict[str, object]] = []
    for snapshot in ordered_snapshots:
        price = _close_price_on_or_before(normalized_close, _snapshot_time(snapshot))
        if price is None:
            continue
        account_equity = _snapshot_equity(snapshot)
        benchmark_equity = starting_equity * (price / start_price)
        points.append(
            {
                "time": _snapshot_time(snapshot),
                "accountEquity": account_equity,
                "benchmarkEquity": benchmark_equity,
            }
        )

    if len(points) < 2:
        return None

    benchmark_equity = coerce_float(points[-1]["benchmarkEquity"])
    account_ending_equity = coerce_float(points[-1]["accountEquity"])
    if benchmark_equity is None or account_ending_equity is None:
        return None
    account_return_pct = ((account_ending_equity / starting_equity) - 1.0) * 100.0
    benchmark_return_pct = ((benchmark_equity / starting_equity) - 1.0) * 100.0
    alpha_pct = account_return_pct - benchmark_return_pct
    return {
        "benchmark": benchmark_ticker,
        "startTime": str(points[0]["time"]),
        "endTime": str(points[-1]["time"]),
        "startingEquity": starting_equity,
        "endingEquity": account_ending_equity,
        "benchmarkEquity": benchmark_equity,
        "accountReturnPct": account_return_pct,
        "benchmarkReturnPct": benchmark_return_pct,
        "alphaPct": alpha_pct,
        "points": points,
    }


def attach_live_benchmark_summary(
    summary: dict[str, object],
    overlay: dict[str, object] | None,
) -> dict[str, object]:
    summary["liveBenchmarkReturnPct"] = overlay["benchmarkReturnPct"] if overlay is not None else None
    summary["liveAlphaPct"] = overlay["alphaPct"] if overlay is not None else None
    summary["liveBenchmarkEquity"] = overlay["benchmarkEquity"] if overlay is not None else None
    summary["liveBenchmarkStartTime"] = overlay["startTime"] if overlay is not None else None
    summary["liveBenchmarkEndTime"] = overlay["endTime"] if overlay is not None else None
    return summary
