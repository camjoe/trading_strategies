from __future__ import annotations

from pydantic import BaseModel, Field

from trading.services.profiles.source import DEFAULT_TICKERS_FILE


class BacktestBaseRequest(BaseModel):
    account: str
    tickersFile: str = DEFAULT_TICKERS_FILE
    universeHistoryDir: str | None = None
    start: str | None = None
    end: str | None = None
    lookbackMonths: int | None = Field(default=None, gt=0)
    allowApproximateLeaps: bool = False


class BacktestRunRequest(BacktestBaseRequest):
    slippageBps: float = 5.0
    fee: float = 0.0
    runName: str | None = None


class BacktestPreflightRequest(BacktestBaseRequest):
    """Preflight-check request — identical shape to the base request."""
