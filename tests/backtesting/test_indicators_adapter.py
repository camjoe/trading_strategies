from __future__ import annotations

import builtins
from types import SimpleNamespace

import pandas as pd
import pytest

from trading.backtesting import indicators_adapter


class TestIndicatorsAdapter:
    def test_get_indicators_module_import_error_has_actionable_message(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        original_import = builtins.__import__

        def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "trends" and "indicators" in fromlist:
                raise ModuleNotFoundError("simulated missing trends package")
            return original_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", _fake_import)

        with pytest.raises(RuntimeError, match="require trends.indicators module"):
            indicators_adapter.get_indicators_module()

    def test_get_indicator_function_rejects_unknown_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub = SimpleNamespace(calculate_macd=lambda _history: None)
        monkeypatch.setattr(indicators_adapter, "get_indicators_module", lambda: stub)

        with pytest.raises(AttributeError, match="Indicator function 'missing_fn' not found"):
            indicators_adapter.get_indicator_function("missing_fn")

    def test_calculate_macd_delegates_to_indicator_module(self, monkeypatch: pytest.MonkeyPatch) -> None:
        history = pd.Series([100.0, 101.0, 102.0])
        expected = (
            pd.Series([1.0, 2.0, 3.0]),
            pd.Series([0.5, 1.5, 2.5]),
            pd.Series([0.5, 0.5, 0.5]),
        )

        monkeypatch.setattr(
            indicators_adapter,
            "get_indicator_function",
            lambda name: (lambda _history: expected) if name == "calculate_macd" else None,
        )

        out = indicators_adapter.calculate_macd(history)

        assert out == expected

    def test_calculate_rs_rsi_passes_window_to_indicator_module(self, monkeypatch: pytest.MonkeyPatch) -> None:
        history = pd.Series([100.0, 101.0, 102.0, 103.0])
        seen_window: dict[str, int] = {}

        def _fn(_history: pd.Series, *, window: int) -> tuple[pd.Series, pd.Series]:
            seen_window["value"] = window
            return pd.Series([1.0] * len(_history)), pd.Series([50.0] * len(_history))

        monkeypatch.setattr(
            indicators_adapter,
            "get_indicator_function",
            lambda name: _fn if name == "calculate_rs_rsi" else None,
        )

        rs, rsi = indicators_adapter.calculate_rs_rsi(history, window=21)

        assert seen_window["value"] == 21
        assert len(rs) == len(history)
        assert len(rsi) == len(history)
