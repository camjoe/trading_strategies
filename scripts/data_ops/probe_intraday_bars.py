"""Probe what the market-data provider returns for today's bar while the market is open.

Intraday trading runs only help if a run sees today's unfinished daily bar and if that bar changes during the
session. This probe fetches the bars the way the auto-trader does (``fetch_ohlcv`` at ``1d``) and reports:

- whether the last bar is dated today (US Eastern),
- whether the provider's on-disk cache returns the same bar as a fresh fetch, and
- whether a fresh fetch after a wait returns a different last bar.

Read-only: it touches no trading data and uses a temporary cache directory, so the real market-data cache is
left alone. It does make network calls to the data vendor, so run it from the host while the market is open.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time as clock
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from trading.services.market_data.protocols import MarketDataProvider

NEW_YORK = ZoneInfo("America/New_York")
_MARKET_OPEN = clock(9, 30)
_MARKET_CLOSE = clock(16, 0)
_CACHE_DIR_ENV = "TRADING_MARKET_DATA_CACHE_DIR"
_CACHE_DISABLED_ENV = "TRADING_MARKET_DATA_CACHE_DISABLED"
_DEFAULT_UNIVERSE = (
    Path(__file__).resolve().parents[2] / "src" / "infrastructure" / "config" / "trade_universes" / "default.txt"
)


@dataclass(frozen=True)
class LastBar:
    """The last row of a bar frame: the day it is dated, and its close and volume."""

    day: date
    close: float
    volume: float


@dataclass(frozen=True)
class TickerProbe:
    ticker: str
    first: LastBar
    cached: LastBar
    fresh: LastBar
    later: LastBar | None


def last_bar(frame: pd.DataFrame) -> LastBar:
    """The last bar of *frame* (``close`` and ``volume`` columns, indexed by date or timestamp)."""
    row = frame.iloc[-1]
    return LastBar(day=pd.Timestamp(frame.index[-1]).date(), close=float(row["close"]), volume=float(row["volume"]))


def market_is_open(now: datetime) -> bool:
    """Whether *now* falls in a regular US session (weekday, 09:30 to 16:00 Eastern; holidays are not known)."""
    local = now.astimezone(NEW_YORK)
    return local.weekday() < 5 and _MARKET_OPEN <= local.time() < _MARKET_CLOSE


def verdicts(probes: Sequence[TickerProbe], today: date, market_open: bool) -> list[str]:
    """Plain-language conclusions from *probes*; each line answers one question."""
    lines: list[str] = []
    if not market_open:
        lines.append(
            "WARNING: the market is closed now, so today's bar and any change in it say little. Re-run in session."
        )
    has_today = [p.ticker for p in probes if p.fresh.day == today]
    lines.append(
        f"Today's bar in a fresh fetch: {len(has_today)} of {len(probes)} tickers"
        + (" (the provider returns the unfinished bar)." if has_today else " (no unfinished bar was returned).")
    )
    stale = [p.ticker for p in probes if p.cached != p.fresh]
    lines.append(
        "The cache returned a different last bar than a fresh fetch for "
        + (f"{', '.join(stale)}." if stale else "no ticker (cache and fresh agree).")
    )
    waited = [p for p in probes if p.later is not None]
    if waited:
        changed = [p.ticker for p in waited if p.later != p.fresh]
        lines.append(
            f"A fresh fetch after the wait changed the last bar for {len(changed)} of {len(waited)} tickers"
            + (
                f" ({', '.join(changed)})."
                if changed
                else " (the bar did not move; see the warning if the market is closed)."
            )
        )
    return lines


def probe_ticker(
    provider: MarketDataProvider,
    ticker: str,
    period: str,
    wait_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
) -> TickerProbe:
    """Fetch *ticker* four ways: first (fills the cache), cached, fresh (cache off), and fresh again after a wait."""
    first = last_bar(provider.fetch_ohlcv(ticker, period, "1d"))
    cached = last_bar(provider.fetch_ohlcv(ticker, period, "1d"))
    previous = os.environ.get(_CACHE_DISABLED_ENV)
    os.environ[_CACHE_DISABLED_ENV] = "1"
    try:
        fresh = last_bar(provider.fetch_ohlcv(ticker, period, "1d"))
        later = None
        if wait_seconds > 0:
            sleep(wait_seconds)
            later = last_bar(provider.fetch_ohlcv(ticker, period, "1d"))
    finally:
        if previous is None:
            os.environ.pop(_CACHE_DISABLED_ENV, None)
        else:
            os.environ[_CACHE_DISABLED_ENV] = previous
    return TickerProbe(ticker, first, cached, fresh, later)


def render(probes: Sequence[TickerProbe]) -> str:
    """One line per ticker with the four last bars."""
    lines = [f"{'ticker':8} {'first':>22} {'cached':>22} {'fresh':>22} {'after wait':>22}"]

    def cell(bar: LastBar | None) -> str:
        return "-" if bar is None else f"{bar.day} {bar.close:.2f} v{bar.volume:.0f}"

    for p in probes:
        lines.append(f"{p.ticker:8} {cell(p.first):>22} {cell(p.cached):>22} {cell(p.fresh):>22} {cell(p.later):>22}")
    return "\n".join(lines)


def default_tickers(count: int) -> list[str]:
    """The first *count* tickers of the default trade universe."""
    names = [line.strip() for line in _DEFAULT_UNIVERSE.read_text(encoding="utf-8").splitlines()]
    return [name for name in names if name and not name.startswith("#")][:count]


def main(argv: Sequence[str] | None = None, provider: MarketDataProvider | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--tickers", default="", help="Comma-separated tickers (default: the first three of the default universe)."
    )
    parser.add_argument("--period", default="3mo", help="Bar history period passed to the provider (default: 3mo).")
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=300.0,
        help="Pause before the last fetch to see the bar move; 0 skips it (default: 300).",
    )
    args = parser.parse_args(argv)
    tickers = [name.strip().upper() for name in args.tickers.split(",") if name.strip()] or default_tickers(3)
    if not tickers:
        print("No tickers to probe.", file=sys.stderr)
        return 1

    previous_dir = os.environ.get(_CACHE_DIR_ENV)
    try:
        with tempfile.TemporaryDirectory() as cache_dir:
            os.environ[_CACHE_DIR_ENV] = cache_dir
            if provider is None:
                from infrastructure.market_data.factory import build_provider

                provider = build_provider()
            now = datetime.now(NEW_YORK)
            print(
                f"Probing {', '.join(tickers)} at {now:%Y-%m-%d %H:%M} Eastern (provider: {type(provider).__name__})."
            )
            probes = [probe_ticker(provider, ticker, args.period, args.wait_seconds) for ticker in tickers]
    finally:
        if previous_dir is None:
            os.environ.pop(_CACHE_DIR_ENV, None)
        else:
            os.environ[_CACHE_DIR_ENV] = previous_dir
    print(render(probes))
    print()
    print("\n".join(verdicts(probes, now.date(), market_is_open(now))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
