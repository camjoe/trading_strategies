from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from trading.domain.exceptions import NotFoundError, ValidationError

from .config import CORS_ORIGINS
from .routes import (
    accounts_router,
    actions_router,
    admin_router,
    analysis_router,
    autonomy_monitor_router,
    backtests_router,
    features_router,
    health_router,
    logs_router,
    portfolio_router,
    strategy_lab_router,
)

app = FastAPI(title="Paper Trading UI API", version="0.1.0")
ALLOW_ALL_CORS = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=ALLOW_ALL_CORS,
    allow_headers=ALLOW_ALL_CORS,
)


@app.exception_handler(NotFoundError)
async def _not_found_handler(_request: Request, exc: NotFoundError) -> JSONResponse:
    """Map a domain not-found error to HTTP 404 (see docs/adr/007-ui-error-mapping.md)."""
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValidationError)
async def _validation_handler(_request: Request, exc: ValidationError) -> JSONResponse:
    """Map a domain validation error to HTTP 400 (see docs/adr/007-ui-error-mapping.md).

    NotFoundError and ValidationError are sibling subclasses of ValueError, so
    Starlette matches each on its own type: NotFoundError still resolves to 404.
    A bare ValueError matches neither handler and surfaces as 500.
    """
    return JSONResponse(status_code=400, content={"detail": str(exc)})


app.include_router(health_router)
app.include_router(accounts_router)
app.include_router(autonomy_monitor_router)
app.include_router(analysis_router)
app.include_router(portfolio_router)
app.include_router(admin_router)
app.include_router(logs_router)
app.include_router(actions_router)
app.include_router(backtests_router)
app.include_router(features_router)
app.include_router(strategy_lab_router)
