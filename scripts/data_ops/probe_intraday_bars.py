"""Probe what the market-data provider returns for today's bar while the market is open.

Fetches bars the way the auto-trader does (``fetch_ohlcv`` at ``1d``) and reports whether the last bar is dated
today (US Eastern), whether two back-to-back fetches differ, and whether a fresh fetch after a wait differs.
Read-only, uses a temporary cache directory, and makes network calls to the data vendor.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone

import pandas as pd

from infrastructure.market_data.demo_provider import DemoMarketDataProvider
from trading.domain.market.hours import US_EQUITY_MARKET_TIMEZONE, is_regular_us_equity_market_open
from trading.services.market_data.protocols import MarketDataProvider
from trading.services.universe import resolve_named_universes

_CACHE_DIR_ENV = "TRADING_MARKET_DATA_CACHE_DIR"
_CACHE_DISABLED_ENV = "TRADING_MARKET_DATA_CACHE_DISABLED"


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
    moved = [p.ticker for p in probes if p.cached != p.fresh]
    lines.append(
        "The last bar changed between two back-to-back fetches for "
        + (
            f"{', '.join(moved)} (a cached copy would serve the older bar)."
            if moved
            else "no ticker (a quiet moment; this does not test an old cache entry)."
        )
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


def probe_tickers(
    provider: MarketDataProvider,
    tickers: Sequence[str],
    period: str,
    wait_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
    say: Callable[[str], None] = print,
) -> list[TickerProbe]:
    """Fetch every ticker three ways, wait once, then fetch each again: first (fills the cache), cached, fresh, later."""
    firsts: dict[str, LastBar] = {}
    cacheds: dict[str, LastBar] = {}
    freshes: dict[str, LastBar] = {}
    for ticker in tickers:
        say(f"Fetching {ticker} ...")
        firsts[ticker] = last_bar(provider.fetch_ohlcv(ticker, period, "1d"))
        cacheds[ticker] = last_bar(provider.fetch_ohlcv(ticker, period, "1d"))
        with _cache_disabled():
            freshes[ticker] = last_bar(provider.fetch_ohlcv(ticker, period, "1d"))
    laters: dict[str, LastBar | None] = dict.fromkeys(tickers)
    if wait_seconds > 0:
        say(f"Waiting {wait_seconds:.0f} seconds, once, before fetching again (Ctrl+C to stop) ...")
        sleep(wait_seconds)
        with _cache_disabled():
            for ticker in tickers:
                laters[ticker] = last_bar(provider.fetch_ohlcv(ticker, period, "1d"))
    return [TickerProbe(t, firsts[t], cacheds[t], freshes[t], laters[t]) for t in tickers]


@contextmanager
def _cache_disabled() -> Iterator[None]:
    """Turn the provider's disk cache off for the block and put the setting back afterwards."""
    previous = os.environ.get(_CACHE_DISABLED_ENV)
    os.environ[_CACHE_DISABLED_ENV] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(_CACHE_DISABLED_ENV, None)
        else:
            os.environ[_CACHE_DISABLED_ENV] = previous


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
    return resolve_named_universes(["default"])[:count]


def main(
    argv: Sequence[str] | None = None,
    provider: MarketDataProvider | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> int:
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
            started = now()
            print(
                f"Probing {', '.join(tickers)} at {started.astimezone(US_EQUITY_MARKET_TIMEZONE):%Y-%m-%d %H:%M} Eastern "
                f"(provider: {type(provider).__name__})."
            )
            probes = probe_tickers(provider, tickers, args.period, args.wait_seconds)
    finally:
        if previous_dir is None:
            os.environ.pop(_CACHE_DIR_ENV, None)
        else:
            os.environ[_CACHE_DIR_ENV] = previous_dir
    print(render(probes))
    print()
    ended = now()
    market_open = is_regular_us_equity_market_open(started) and is_regular_us_equity_market_open(ended)
    today = started.astimezone(US_EQUITY_MARKET_TIMEZONE).date()
    if isinstance(provider, DemoMarketDataProvider):
        print("WARNING: the demo provider generated these bars, so none of the conclusions describe the vendor.")
    print("\n".join(verdicts(probes, today, market_open)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
