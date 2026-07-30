"""The sweep data context must be a pure speed-up: same answers, fewer reads."""

from __future__ import annotations

from datetime import date

import pytest

import trading.backtesting.backtest as backtest_module
from tests.support.backtesting import create_backtest_account, make_backtest_config
from trading.backtesting.services.backtest_data_context import BacktestDataContext
from trading.services.market_data import FeatureBundle

EMPTY_BUNDLE = FeatureBundle(ticker_features={})


class TestSweepRunFunctions:
    def test_shared_context_yields_identical_results_to_per_run_contexts(self, conn, bt_market_data) -> None:
        """The whole change is a cache; a cached run that answers differently is a bug.

        Metrics are compared rather than run ids because the persisted run writes a
        new row each time — the simulation's conclusions are what must not move.
        """
        create_backtest_account(conn, "acct_ctx_equiv")
        bt_market_data(["AAPL", "MSFT"], [100.0, 103.0])
        cfg = make_backtest_config("acct_ctx_equiv")

        uncached = backtest_module.run_backtest_metrics_only(conn, cfg)
        run_metrics_only, _run_persisted = backtest_module.sweep_run_functions(conn)
        first_cached = run_metrics_only(conn, cfg)
        second_cached = run_metrics_only(conn, cfg)

        for cached in (first_cached, second_cached):
            assert cached.total_return_pct == uncached.total_return_pct
            assert cached.max_drawdown_pct == uncached.max_drawdown_pct
            assert cached.trade_count == uncached.trade_count
            assert cached.ending_equity == uncached.ending_equity
            assert cached.benchmark_return_pct == uncached.benchmark_return_pct

    def test_repeated_runs_over_one_span_read_price_history_once(self, conn, bt_market_data, monkeypatch) -> None:
        """The saving itself: candidates sharing a span share the fetch.

        Without this the context is just indirection — the redundant per-candidate
        reads it exists to remove would still happen.
        """
        create_backtest_account(conn, "acct_ctx_reads")
        bt_market_data(["AAPL", "MSFT"], [100.0, 103.0])
        cfg = make_backtest_config("acct_ctx_reads")

        fetches: list[tuple[str, ...]] = []
        inner = backtest_module.fetch_close_history

        def counting_fetch(tickers, start_date, end_date, **kwargs):
            fetches.append(tuple(tickers))
            return inner(tickers, start_date, end_date, **kwargs)

        monkeypatch.setattr(backtest_module, "fetch_close_history", counting_fetch)

        run_metrics_only, _run_persisted = backtest_module.sweep_run_functions(conn)
        run_metrics_only(conn, cfg)
        run_metrics_only(conn, cfg)
        run_metrics_only(conn, cfg)

        assert len(fetches) == 1

    def test_a_different_span_is_fetched_separately(self, conn, bt_market_data, monkeypatch) -> None:
        """Windows differ by date, so each window must still get its own history."""
        create_backtest_account(conn, "acct_ctx_spans")
        bt_market_data(["AAPL", "MSFT"], [100.0, 103.0])

        fetches: list[tuple[str, ...]] = []
        inner = backtest_module.fetch_close_history

        def counting_fetch(tickers, start_date, end_date, **kwargs):
            fetches.append(tuple(tickers))
            return inner(tickers, start_date, end_date, **kwargs)

        monkeypatch.setattr(backtest_module, "fetch_close_history", counting_fetch)

        run_metrics_only, _run_persisted = backtest_module.sweep_run_functions(conn)
        run_metrics_only(conn, make_backtest_config("acct_ctx_spans", start="2026-01-01", end="2026-02-01"))
        run_metrics_only(conn, make_backtest_config("acct_ctx_spans", start="2026-01-01", end="2026-02-20"))

        assert len(fetches) == 2

    def test_a_plain_run_does_not_share_a_context_with_a_later_one(self, conn, bt_market_data, monkeypatch) -> None:
        """A context must never outlive its run, or a later run inherits stale prices."""
        create_backtest_account(conn, "acct_ctx_fresh")
        bt_market_data(["AAPL", "MSFT"], [100.0, 103.0])
        cfg = make_backtest_config("acct_ctx_fresh")

        fetches: list[tuple[str, ...]] = []
        inner = backtest_module.fetch_close_history

        def counting_fetch(tickers, start_date, end_date, **kwargs):
            fetches.append(tuple(tickers))
            return inner(tickers, start_date, end_date, **kwargs)

        monkeypatch.setattr(backtest_module, "fetch_close_history", counting_fetch)

        backtest_module.run_backtest_metrics_only(conn, cfg)
        backtest_module.run_backtest_metrics_only(conn, cfg)

        assert len(fetches) == 2


class TestConnectionBinding:
    def test_a_second_connection_is_refused(self, conn) -> None:
        """Account and book entries are keyed by name and id alone, which is only
        sound while the context reads through the connection it was built for."""
        context = backtest_module.build_backtest_data_context(conn)

        with pytest.raises(ValueError, match="bound to one connection"):
            context.get_account(object(), "acct_any")  # type: ignore[arg-type]


class TestFeatureBundleCaching:
    def test_one_bundle_is_built_per_ticker_span(self, conn) -> None:
        """Feature strategies pay a proxy fetch per bundle; candidates share a span."""
        builds: list[tuple[str, ...]] = []

        class CountingFeatureProvider:
            def build_feature_bundle(self, tickers, start_date, end_date, close_history):
                builds.append(tuple(tickers))
                return EMPTY_BUNDLE

        context = BacktestDataContext(
            conn=conn,
            feature_provider=CountingFeatureProvider(),  # type: ignore[arg-type]
            get_account_fn=lambda _conn, _name: None,
            get_default_book_fn=lambda _conn, **_kwargs: None,
            resolve_universe_fn=lambda _cfg, _start, _end: ([], {}, [], []),
            fetch_close_history_fn=lambda _tickers, _start, _end: None,
            fetch_benchmark_close_fn=lambda _ticker, _start, _end: None,
        )

        span = (date(2026, 1, 1), date(2026, 2, 1))
        context.build_feature_bundle(["AAPL"], *span, None)  # type: ignore[arg-type]
        context.build_feature_bundle(["AAPL"], *span, None)  # type: ignore[arg-type]
        context.build_feature_bundle(["AAPL"], date(2026, 1, 1), date(2026, 3, 1), None)  # type: ignore[arg-type]

        assert len(builds) == 2
