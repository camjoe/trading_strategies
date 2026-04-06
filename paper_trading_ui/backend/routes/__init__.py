from __future__ import annotations

from .actions import router as actions_router
from .accounts import router as accounts_router
from .admin import router as admin_router
from .backtests import router as backtests_router
from .features import router as features_router
from .health import router as health_router
from .logs import router as logs_router
from .trades import router as trades_router

__all__ = [
    "actions_router",
    "accounts_router",
    "admin_router",
    "backtests_router",
    "features_router",
    "health_router",
    "logs_router",
    "trades_router",
]
