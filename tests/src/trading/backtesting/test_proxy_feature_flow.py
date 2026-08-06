from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import trading.backtesting.backtest as backtest_module
import trading.backtesting.services.execution_service as execution_service
from tests.support.backtesting import (
    create_backtest_account,
    install_backtest_market_data,
)
from trading.services.market_data import FeatureBundle, ProxyFeatureDataProvider


class TestBacktestProxyFeatureFlow:
    def test_proxy_feature_provider_builds_aligned_topic_features(
        self,
        tmp_path: Path,
    ) -> None:
        idx = pd.date_range("2026-01-01", periods=40, freq="B")
        close_history = pd.DataFrame(
            {
                "AAPL": [100.0 + i for i in range(40)],
                "XOM": [80.0 + (i * 0.5) for i in range(40)],
            },
            index=idx,
        )

        category_file = tmp_path / "ticker_categories.txt"
        category_file.write_text("[tech]\nAAPL\n[energy]\nXOM\n", encoding="utf-8")

        proxy_index = pd.date_range("2025-11-01", periods=90, freq="B")
        proxy_frame = pd.DataFrame(
            {
                "SPY": [100.0 + (i * 0.2) for i in range(90)],
                "XLK": [100.0 + (i * 0.35) for i in range(90)],
                "XLE": [100.0 + (i * 0.25) for i in range(90)],
                "TLT": [100.0 + (i * 0.05) for i in range(90)],
                "^VIX": [20.0 + ((i % 5) * 0.1) for i in range(90)],
            },
            index=proxy_index,
        )

        class StubProvider:
            def fetch_close_history(self, tickers: list[str], _start, _end) -> pd.DataFrame:
                return proxy_frame.loc[:, tickers]

        provider = ProxyFeatureDataProvider(
            category_file=str(category_file),
            market_data_provider=StubProvider(),
        )
        bundle = provider.build_feature_bundle(["AAPL", "XOM"], date(2026, 1, 1), date(2026, 3, 1), close_history)

        aapl_features = bundle.history_for_ticker("AAPL", idx[-1])
        assert aapl_features is not None
        assert "topic_proxy_rel_strength" in aapl_features.columns
        assert float(aapl_features["topic_proxy_available"].iloc[-1]) == 1.0
        assert pd.notna(aapl_features["macro_risk_on_score"].iloc[-1])

    def test_run_backtest_passes_feature_history_for_proxy_strategies(
        self,
        conn,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        create_backtest_account(conn, "acct_topic", strategy="trend")
        install_backtest_market_data(monkeypatch, backtest_module, tickers=["AAPL"], benchmark_values=[100.0, 101.0])

        idx = pd.date_range("2026-01-01", periods=40, freq="B")
        feature_frame = pd.DataFrame(
            {
                "topic_proxy_available": [1.0] * 40,
                "topic_proxy_rel_strength": [0.02] * 40,
                "topic_proxy_trend_gap": [0.01] * 40,
            },
            index=idx,
        )

        class StubFeatureProvider:
            def build_feature_bundle(self, _tickers, _start, _end, _close_history) -> FeatureBundle:
                return FeatureBundle(ticker_features={"AAPL": feature_frame})

        call_count = {"n": 0}

        def fake_signal(
            _strategy_name: str,
            _history: pd.Series,
            _params: dict[str, object],
            feature_history: pd.DataFrame | None = None,
        ) -> str:
            call_count["n"] += 1
            assert feature_history is not None
            assert "topic_proxy_rel_strength" in feature_history.columns
            return "hold"

        # No strategy in the registry declares required_features today, so the spec
        # is stubbed: the behaviour under test is the engine wiring � a strategy
        # that declares features gets a bundle built and per-ticker history passed
        # to its signal � not any particular strategy.
        monkeypatch.setattr(
            execution_service,
            "resolve_strategy",
            lambda _name: SimpleNamespace(
                indicators=(),
                required_features=("topic_proxy_rel_strength",),
                strategy_id="trend",
                default_params={},
            ),
        )
        monkeypatch.setattr(backtest_module, "build_feature_provider", lambda **_kwargs: StubFeatureProvider())
        monkeypatch.setattr(execution_service, "evaluate_signal", fake_signal)

        backtest_module.run_backtest(
            conn,
            backtest_module.BacktestConfig(
                account_name="acct_topic",
                tickers_file="src/infrastructure/config/trade_universes/default.txt",
                universe_history_dir=None,
                start="2026-01-01",
                end="2026-03-01",
                lookback_months=None,
                slippage_bps=5.0,
                fee_per_trade=0.0,
                run_name="topic-proxy",
                allow_approximate_leaps=False,
            ),
        )

        assert call_count["n"] > 0
