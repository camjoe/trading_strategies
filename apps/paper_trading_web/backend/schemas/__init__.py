"""Pydantic request schemas for the paper-trading UI backend."""

from __future__ import annotations

from .accounts import AccountParamsRequest, BookParamsRequest
from .admin import AdminCreateAccountRequest, AdminDeleteAccountRequest
from .backtests import (
    BacktestBaseRequest,
    BacktestPreflightRequest,
    BacktestRunRequest,
)
from .catalog import CatalogRunRequest
from .features import FeatureSignalsRequest
from .strategy_lab import (
    ConfigureStrategyRequest,
    CreateStrategyVariantRequest,
    PromoteOptimizationRequest,
    RunOptimizationRequest,
)

__all__ = [
    "AccountParamsRequest",
    "BookParamsRequest",
    "AdminCreateAccountRequest",
    "AdminDeleteAccountRequest",
    "BacktestBaseRequest",
    "BacktestPreflightRequest",
    "BacktestRunRequest",
    "CatalogRunRequest",
    "FeatureSignalsRequest",
    "ConfigureStrategyRequest",
    "CreateStrategyVariantRequest",
    "PromoteOptimizationRequest",
    "RunOptimizationRequest",
]
