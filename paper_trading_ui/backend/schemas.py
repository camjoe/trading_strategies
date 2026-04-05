from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, Field

from trading.services.profile_source import DEFAULT_TICKERS_FILE


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


class WalkForwardRunRequest(BacktestBaseRequest):
    testMonths: int = Field(default=1, gt=0)
    stepMonths: int = Field(default=1, gt=0)
    slippageBps: float = 5.0
    fee: float = 0.0
    runNamePrefix: str | None = None


class BacktestPreflightRequest(BacktestBaseRequest):
    pass


class TestInvestmentRow(TypedDict):
    ticker: str
    amount: float


class AdminCreateAccountRequest(BaseModel):
    name: str
    strategy: str
    initialCash: float = Field(gt=0)
    benchmarkTicker: str = "SPY"
    descriptiveName: str | None = None
    goalMinReturnPct: float | None = None
    goalMaxReturnPct: float | None = None
    goalPeriod: str = "monthly"
    learningEnabled: bool = False
    riskPolicy: str = "none"
    stopLossPct: float | None = None
    takeProfitPct: float | None = None
    instrumentMode: str = "equity"
    optionStrikeOffsetPct: float | None = None
    optionMinDte: int | None = None
    optionMaxDte: int | None = None
    optionType: str | None = None
    targetDeltaMin: float | None = None
    targetDeltaMax: float | None = None
    maxPremiumPerTrade: float | None = None
    maxContractsPerTrade: int | None = None
    ivRankMin: float | None = None
    ivRankMax: float | None = None
    rollDteThreshold: int | None = None
    profitTakePct: float | None = None
    maxLossPct: float | None = None
    rotationEnabled: bool = False
    rotationMode: str = "time"
    rotationOptimalityMode: str = "previous_period_best"
    rotationIntervalDays: int | None = None
    rotationLookbackDays: int | None = None
    rotationSchedule: list[str] | None = None
    rotationActiveIndex: int = 0
    rotationLastAt: str | None = None
    rotationActiveStrategy: str | None = None


class AdminDeleteAccountRequest(BaseModel):
    accountName: str
    confirm: bool = False


class AccountParamsRequest(BaseModel):
    strategy: str | None = None
    riskPolicy: str | None = None


class ManualTradeRequest(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    qty: float = Field(gt=0)
    price: float = Field(gt=0)
    fee: float = Field(default=0.0, ge=0)
