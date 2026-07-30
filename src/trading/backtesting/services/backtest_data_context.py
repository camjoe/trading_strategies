"""Memoize the inputs a backtest reads before it simulates anything.

A walk-forward sweep runs ``candidates x windows`` simulations that differ only
in parameter override and window dates. The account record, its default book,
the resolved universe membership, the price history, and the feature bundle are
functions of the account, universe, and date span — never of the candidate's
parameters — so within one window every candidate was re-reading identical data.

One context per single backtest memoizes nothing useful and costs nothing; one
context shared across a sweep turns per-candidate reads into per-window reads.
That is the whole difference: lifetime, not logic.

Every read is injected from the composition seam that builds the providers, so
this module is a cache and nothing else — it resolves no adapters of its own.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any, Callable

import pandas as pd

from trading.services.market_data import FeatureBundle, FeatureDataProvider

GetAccountFn = Callable[[sqlite3.Connection, str], Any]
GetDefaultBookFn = Callable[..., Any]
ResolveUniverseFn = Callable[[Any, date, date], tuple[list[str], dict[str, list[str]], list[str], list[str]]]
FetchCloseHistoryFn = Callable[[list[str], date, date], pd.DataFrame]
FetchBenchmarkCloseFn = Callable[[str, date, date], pd.Series]


class BacktestDataContext(FeatureDataProvider):
    """The pre-simulation reads of one backtest, or of one whole sweep.

    Bound to a single connection, and deliberately short-lived: a context never
    outlives the run (or sweep) it was built for, so it cannot serve stale market
    data to a later one.

    Cached frames are handed out by reference rather than copied — that is where
    the saving comes from — so every consumer must treat them as read-only. The
    simulation loop and the feature builder both already derive new objects
    (``.loc[...]``, ``.dropna()``, ``pd.to_datetime(...)``) rather than mutating
    what they were given.

    Implements ``FeatureDataProvider`` by delegating to the injected one and
    caching the bundle, so it can be passed wherever a feature provider is
    expected.
    """

    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        feature_provider: FeatureDataProvider,
        get_account_fn: GetAccountFn,
        get_default_book_fn: GetDefaultBookFn,
        resolve_universe_fn: ResolveUniverseFn,
        fetch_close_history_fn: FetchCloseHistoryFn,
        fetch_benchmark_close_fn: FetchBenchmarkCloseFn,
    ) -> None:
        self._conn = conn
        self._feature_provider = feature_provider
        self._get_account_fn = get_account_fn
        self._get_default_book_fn = get_default_book_fn
        self._resolve_universe_fn = resolve_universe_fn
        self._fetch_close_history_fn = fetch_close_history_fn
        self._fetch_benchmark_close_fn = fetch_benchmark_close_fn
        self._accounts: dict[str, Any] = {}
        self._books: dict[int, Any] = {}
        self._universes: dict[
            tuple[str, str | None, date, date], tuple[list[str], dict[str, list[str]], list[str], list[str]]
        ] = {}
        self._close_history: dict[tuple[tuple[str, ...], date, date], pd.DataFrame] = {}
        self._benchmarks: dict[tuple[str, date, date], pd.Series] = {}
        self._feature_bundles: dict[tuple[tuple[str, ...], date, date], FeatureBundle] = {}

    def _require_bound_connection(self, conn: sqlite3.Connection) -> None:
        """Guard the assumption the DB caches rest on.

        Account and book entries are keyed by name and id alone, which is only
        sound while every read goes through the connection the context was built
        for. Reusing a context across connections would silently serve one
        database's rows to another.
        """
        if conn is not self._conn:
            raise ValueError("BacktestDataContext is bound to one connection; build a new context per run or sweep.")

    def get_account(self, conn: sqlite3.Connection, name: str) -> Any:
        self._require_bound_connection(conn)
        if name not in self._accounts:
            self._accounts[name] = self._get_account_fn(conn, name)
        return self._accounts[name]

    def get_default_book(self, conn: sqlite3.Connection, *, account_id: int) -> Any:
        self._require_bound_connection(conn)
        if account_id not in self._books:
            self._books[account_id] = self._get_default_book_fn(conn, account_id=account_id)
        return self._books[account_id]

    def resolve_universe(
        self,
        cfg: Any,
        start_date: date,
        end_date: date,
    ) -> tuple[list[str], dict[str, list[str]], list[str], list[str]]:
        # Membership depends on the ticker source and the span, not on anything
        # else the config carries.
        key = (cfg.tickers_file, cfg.universe_history_dir, start_date, end_date)
        if key not in self._universes:
            self._universes[key] = self._resolve_universe_fn(cfg, start_date, end_date)
        return self._universes[key]

    def fetch_close_history(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        key = (tuple(tickers), start_date, end_date)
        if key not in self._close_history:
            self._close_history[key] = self._fetch_close_history_fn(tickers, start_date, end_date)
        return self._close_history[key]

    def fetch_benchmark_close(self, benchmark_ticker: str, start_date: date, end_date: date) -> pd.Series:
        key = (benchmark_ticker, start_date, end_date)
        if key not in self._benchmarks:
            self._benchmarks[key] = self._fetch_benchmark_close_fn(benchmark_ticker, start_date, end_date)
        return self._benchmarks[key]

    def build_feature_bundle(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
        close_history: pd.DataFrame,
    ) -> FeatureBundle:
        # The bundle is derived from close_history, which is itself determined by
        # the tickers and span — so those three key the cache.
        key = (tuple(tickers), start_date, end_date)
        if key not in self._feature_bundles:
            self._feature_bundles[key] = self._feature_provider.build_feature_bundle(
                tickers, start_date, end_date, close_history
            )
        return self._feature_bundles[key]
