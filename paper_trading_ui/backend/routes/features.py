"""Feature-provider status and alt-strategy signal endpoints.

GET  /api/features/status  — health probe all three alt-strategy providers
POST /api/features/signals — run alt-strategy signals for a given ticker

All provider/signal logic lives in ``paper_trading_ui.backend.services.features``.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..schemas import FeatureSignalsRequest
from ..services import get_provider_status, get_signals

router = APIRouter()


@router.get("/api/features/status")
def api_feature_status() -> dict[str, list[dict[str, Any]]]:
    """Probe all three alt-strategy feature providers and return their status."""
    return {"providers": get_provider_status()}


@router.post("/api/features/signals")
def api_feature_signals(body: FeatureSignalsRequest) -> dict[str, Any]:
    """Run all three alt-strategy signal functions for the requested ticker.

    Signals are feature-only (no live price history supplied).  The momentum
    guards will fire, so ``available`` is always ``False``.  Use results as
    directional context only.
    """
    ticker = body.ticker.strip().upper()
    return {"ticker": ticker, "signals": get_signals(ticker)}
