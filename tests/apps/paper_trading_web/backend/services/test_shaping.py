from __future__ import annotations

from paper_trading_web.backend.services.shaping import camelize_keys


def test_camelize_keys_converts_nested_dicts_and_lists() -> None:
    payload = {
        "account_return_pct": 1.0,
        "top_winners": [{"avg_cost": 10.0, "unrealized_pnl_pct": -5.0, "ticker": "AAPL"}],
        "points": [{"account_equity": 1.0, "benchmark_equity": 2.0}],
        "equity": 3.0,
        "improvement_notes": ["a", "b"],
    }

    assert camelize_keys(payload) == {
        "accountReturnPct": 1.0,
        "topWinners": [{"avgCost": 10.0, "unrealizedPnlPct": -5.0, "ticker": "AAPL"}],
        "points": [{"accountEquity": 1.0, "benchmarkEquity": 2.0}],
        "equity": 3.0,
        "improvementNotes": ["a", "b"],
    }


def test_camelize_keys_passes_through_none_and_scalars() -> None:
    assert camelize_keys(None) is None
    assert camelize_keys(5) == 5
    assert camelize_keys("x") == "x"
    assert camelize_keys([1, 2]) == [1, 2]
