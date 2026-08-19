"""Response shaping for the account performance-analysis endpoint.

``trading.services.analysis.queries.fetch_account_analysis`` returns a snake_case
domain payload; this maps it to the frontend's camelCase, field by field, the way
every other payload at this boundary is shaped (UI Backend Boundary Rule).
"""

from __future__ import annotations

from typing import Any


def _position_payload(position: dict[str, Any]) -> dict[str, object]:
    return {
        "ticker": position["ticker"],
        "qty": position["qty"],
        "avgCost": position["avg_cost"],
        "costBasis": position["cost_basis"],
        "marketPrice": position["market_price"],
        "marketValue": position["market_value"],
        "unrealizedPnl": position["unrealized_pnl"],
        "unrealizedPnlPct": position["unrealized_pnl_pct"],
        "portfolioPct": position["portfolio_pct"],
    }


def build_account_analysis_payload(analysis: dict[str, Any]) -> dict[str, object]:
    """camelCase response for GET /api/accounts/{name}/analysis."""
    return {
        "accountReturnPct": analysis["account_return_pct"],
        "benchmarkReturnPct": analysis["benchmark_return_pct"],
        "benchmarkTicker": analysis["benchmark_ticker"],
        "alphaPct": analysis["alpha_pct"],
        "realizedPnl": analysis["realized_pnl"],
        "unrealizedPnl": analysis["unrealized_pnl"],
        "equity": analysis["equity"],
        "topWinners": [_position_payload(position) for position in analysis["top_winners"]],
        "topLosers": [_position_payload(position) for position in analysis["top_losers"]],
        "improvementNotes": analysis["improvement_notes"],
    }


__all__ = ["build_account_analysis_payload"]
