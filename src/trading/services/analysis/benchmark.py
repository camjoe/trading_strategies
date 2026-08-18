"""Benchmark overlay calculation helpers for reporting consumers.

Provides utilities to fetch close-price history for a benchmark ticker and
compute a side-by-side return overlay against a sequence of account equity
snapshots.  All functions are side-effect-free with respect to the database;
the only I/O is the market-data provider call in ``fetch_benchmark_close_history``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pandas as pd

from common.coercion import coerce_float
from common.constants import PERCENT_SCALE
from trading.models.portfolio import EquitySnapshotRecord
from trading.services.market_data.lookups import extract_close_series
from trading.services.market_data.protocols import MarketDataProvider, require_provider


def _snapshot_time(snapshot: EquitySnapshotRecord) -> str:
    return snapshot.snapshot_time


def _snapshot_equity(snapshot: EquitySnapshotRecord) -> float:
    return snapshot.equity


def fetch_benchmark_close_history(
    benchmark_ticker: str,
    *,
    start_date: date,
    end_date: date,
    provider: MarketDataProvider | None = None,
) -> pd.Series | None:
    """Fetch daily close prices for *benchmark_ticker* over [start_date, end_date].

    Returns a ``pd.Series`` indexed by date on success, or ``None`` when the
    provider returns no data for the requested ticker and period.
    """
    ticker = benchmark_ticker.strip().upper()
    if not ticker:
        return None
    close_history = require_provider(provider).fetch_close_history([ticker], start_date, end_date)
    return extract_close_series(close_history, ticker)


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
    benchmark_ticker: str,
    snapshots: Sequence[EquitySnapshotRecord],
    *,
    provider: MarketDataProvider | None = None,
) -> dict[str, object] | None:
    """Compute a time-aligned benchmark return overlay for an account's snapshot history.

    Parameters
    ----------
    benchmark_ticker:
        The ticker symbol to use as the benchmark (e.g. ``"SPY"``).
    snapshots:
        Ordered or unordered sequence of ``EquitySnapshotRecord`` rows, each
        carrying ``snapshot_time`` (ISO-8601 string) and ``equity`` (numeric).

    Returns
    -------
    dict or None
        Overlay dict with ``benchmark``, ``startTime``, ``endTime``,
        ``benchmarkReturnPct``, ``alphaPct``, ``points``, and related summary
        fields; or ``None`` when insufficient data is available.
    """
    if len(snapshots) < 2:
        return None

    ordered_snapshots = sorted(list(snapshots), key=_snapshot_time)
    starting_equity = _snapshot_equity(ordered_snapshots[0])
    if starting_equity <= 0:
        return None

    ticker = benchmark_ticker.strip().upper()
    if not ticker:
        return None

    start_date = date.fromisoformat(_snapshot_time(ordered_snapshots[0])[:10])
    end_date = date.fromisoformat(_snapshot_time(ordered_snapshots[-1])[:10])
    try:
        close_history = fetch_benchmark_close_history(
            ticker,
            start_date=start_date,
            end_date=end_date,
            provider=provider,
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

    ending_benchmark_equity = coerce_float(points[-1]["benchmarkEquity"])
    account_ending_equity = coerce_float(points[-1]["accountEquity"])
    if ending_benchmark_equity is None or account_ending_equity is None:
        return None
    account_return_pct = ((account_ending_equity / starting_equity) - 1.0) * PERCENT_SCALE
    benchmark_return_pct = ((ending_benchmark_equity / starting_equity) - 1.0) * PERCENT_SCALE
    alpha_pct = account_return_pct - benchmark_return_pct
    return {
        "benchmark": ticker,
        "startTime": str(points[0]["time"]),
        "endTime": str(points[-1]["time"]),
        "startingEquity": starting_equity,
        "endingEquity": account_ending_equity,
        "benchmarkEquity": ending_benchmark_equity,
        "accountReturnPct": account_return_pct,
        "benchmarkReturnPct": benchmark_return_pct,
        "alphaPct": alpha_pct,
        "points": points,
    }


def attach_live_benchmark_summary(
    summary: dict[str, object],
    overlay: dict[str, object] | None,
) -> dict[str, object]:
    """Inject benchmark summary fields into *summary* from a computed *overlay*.

    Sets ``liveBenchmarkReturnPct``, ``liveAlphaPct``, ``liveBenchmarkEquity``,
    ``liveBenchmarkStartTime``, and ``liveBenchmarkEndTime``.  All fields are
    set to ``None`` when *overlay* is ``None`` (benchmark unavailable).
    """
    summary["liveBenchmarkReturnPct"] = overlay["benchmarkReturnPct"] if overlay is not None else None
    summary["liveAlphaPct"] = overlay["alphaPct"] if overlay is not None else None
    summary["liveBenchmarkEquity"] = overlay["benchmarkEquity"] if overlay is not None else None
    summary["liveBenchmarkStartTime"] = overlay["startTime"] if overlay is not None else None
    summary["liveBenchmarkEndTime"] = overlay["endTime"] if overlay is not None else None
    return summary


__all__ = [
    "attach_live_benchmark_summary",
    "build_live_benchmark_overlay",
    "fetch_benchmark_close_history",
]
