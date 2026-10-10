from __future__ import annotations

from typing import Any

from paper_trading_web.backend.services.analysis import build_account_analysis_payload


def _position(**overrides: Any) -> dict[str, Any]:
    base = {
        "ticker": "AAPL",
        "qty": 10.0,
        "avg_cost": 100.0,
        "cost_basis": 1000.0,
        "market_price": 110.0,
        "market_value": 1100.0,
        "unrealized_pnl": 100.0,
        "unrealized_pnl_pct": 10.0,
        "portfolio_pct": 50.0,
    }
    base.update(overrides)
    return base


def test_build_account_analysis_payload_shapes_camelcase() -> None:
    analysis = {
        "account_return_pct": 1.0,
        "benchmark_return_pct": 0.5,
        "benchmark_ticker": "SPY",
        "alpha_pct": 0.5,
        "realized_pnl": 12.0,
        "unrealized_pnl": 34.0,
        "equity": 5000.0,
        "top_winners": [_position()],
        "top_losers": [_position(ticker="MSFT", unrealized_pnl_pct=-5.0)],
        "improvement_notes": ["note a", "note b"],
    }

    assert build_account_analysis_payload(analysis) == {
        "accountReturnPct": 1.0,
        "benchmarkReturnPct": 0.5,
        "benchmarkTicker": "SPY",
        "alphaPct": 0.5,
        "realizedPnl": 12.0,
        "unrealizedPnl": 34.0,
        "equity": 5000.0,
        "topWinners": [
            {
                "ticker": "AAPL",
                "qty": 10.0,
                "avgCost": 100.0,
                "costBasis": 1000.0,
                "marketPrice": 110.0,
                "marketValue": 1100.0,
                "unrealizedPnl": 100.0,
                "unrealizedPnlPct": 10.0,
                "portfolioPct": 50.0,
            }
        ],
        "topLosers": [
            {
                "ticker": "MSFT",
                "qty": 10.0,
                "avgCost": 100.0,
                "costBasis": 1000.0,
                "marketPrice": 110.0,
                "marketValue": 1100.0,
                "unrealizedPnl": 100.0,
                "unrealizedPnlPct": -5.0,
                "portfolioPct": 50.0,
            }
        ],
        "improvementNotes": ["note a", "note b"],
    }
