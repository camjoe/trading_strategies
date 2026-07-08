from __future__ import annotations

from pydantic import BaseModel, Field


class AdminCreateAccountRequest(BaseModel):
    name: str
    strategy: str
    initialCash: float = Field(gt=0)
    benchmarkTicker: str = "SPY"
    accountKind: str = "managed"
    descriptiveName: str | None = None
    goalMinReturnPct: float | None = None
    goalMaxReturnPct: float | None = None
    goalPeriod: str = "monthly"
    learningEnabled: bool = False
    riskPolicy: str = "none"
    stopLossPct: float | None = None
    takeProfitPct: float | None = None
    tradeSizePct: float | None = None
    maxPositionPct: float | None = None
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
    rotationIntervalDays: int | None = None
    rotationIntervalMinutes: int | None = None
    rotationLookbackDays: int | None = None
    rotationSchedule: list[str] | None = None
    rotationActiveIndex: int = 0
    rotationLastAt: str | None = None
    rotationActiveStrategy: str | None = None


class AdminDeleteAccountRequest(BaseModel):
    accountName: str
    confirm: bool = False
