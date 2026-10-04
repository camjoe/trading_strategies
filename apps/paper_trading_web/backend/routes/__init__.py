from __future__ import annotations

from .accounts import router as accounts_router
from .actions import router as actions_router
from .admin import router as admin_router
from .analysis import router as analysis_router
from .autonomy_monitor import router as autonomy_monitor_router
from .backtests import router as backtests_router
from .features import router as features_router
from .health import router as health_router
from .logs import router as logs_router
from .portfolio import router as portfolio_router
from .strategy_lab import router as strategy_lab_router

__all__ = [
    "actions_router",
    "accounts_router",
    "admin_router",
    "analysis_router",
    "backtests_router",
    "features_router",
    "health_router",
    "autonomy_monitor_router",
    "logs_router",
    "portfolio_router",
    "strategy_lab_router",
]
