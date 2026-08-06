"""Shared passive data contracts used across trading layers.

The lowest layer: all passive data contracts (`*Config`/`*Insert`/`*Record`,
state/order models, and domain value objects) live here, organized into feature
modules. This package imports nothing from `domain`/`services`/`repositories`/
`interfaces`/`infrastructure` (enforced by `scripts/checks/layer_check.py`). The
package root re-exports the stable public types. See
`docs/adr/005-models-as-lowest-data-layer.md`.
"""

from __future__ import annotations

from trading.models.accounts import AccountConfig, AccountDeletionPreview, AccountInsert, AccountRecord, AccountState
from trading.models.execution import RiskGatePosition
from trading.models.orders import BrokerOrder, OrderFill, OrderStatus, OrderType, TimeInForce
from trading.models.parameters import ParameterEntry, ParameterGroup, ParameterSourceView
from trading.models.portfolio import (
    AccountExposure,
    DailyMetricRecord,
    EquitySnapshotRecord,
    PortfolioConcentration,
    PortfolioExposureRollup,
    SectorConcentration,
    SymbolConcentration,
)
from trading.models.rotation import BookRotationConfig
from trading.models.settings import GlobalSettingsRecord

__all__ = [
    "AccountConfig",
    "AccountDeletionPreview",
    "AccountExposure",
    "AccountInsert",
    "AccountRecord",
    "AccountState",
    "BrokerOrder",
    "DailyMetricRecord",
    "EquitySnapshotRecord",
    "GlobalSettingsRecord",
    "OrderFill",
    "OrderStatus",
    "OrderType",
    "ParameterEntry",
    "ParameterGroup",
    "ParameterSourceView",
    "PortfolioConcentration",
    "PortfolioExposureRollup",
    "BookRotationConfig",
    "RiskGatePosition",
    "SectorConcentration",
    "SymbolConcentration",
    "TimeInForce",
]
