from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGINS
from .routes import (
    actions_router,
    accounts_router,
    admin_router,
    analysis_router,
    backtests_router,
    features_router,
    health_router,
    logs_router,
    trades_router,
)

app = FastAPI(title="Paper Trading UI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(accounts_router)
app.include_router(analysis_router)
app.include_router(admin_router)
app.include_router(logs_router)
app.include_router(actions_router)
app.include_router(backtests_router)
app.include_router(trades_router)
app.include_router(features_router)
