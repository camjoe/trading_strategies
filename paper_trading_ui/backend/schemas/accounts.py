from __future__ import annotations

from pydantic import BaseModel


class AccountParamsRequest(BaseModel):
    strategy: str | None = None
    accountKind: str | None = None
    descriptiveName: str | None = None
    riskPolicy: str | None = None
    stopLossPct: float | None = None
    takeProfitPct: float | None = None
    tradeSizePct: float | None = None
    maxPositionPct: float | None = None
    instrumentMode: str | None = None
    goalMinReturnPct: float | None = None
    goalMaxReturnPct: float | None = None
    goalPeriod: str | None = None
    learningEnabled: bool | None = None
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
    rotationEnabled: bool | None = None
    rotationMode: str | None = None
    rotationOptimalityMode: str | None = None
    rotationIntervalDays: int | None = None
    rotationIntervalMinutes: int | None = None
    rotationLookbackDays: int | None = None
    rotationSchedule: list[str] | None = None
    rotationRegimeStrategyRiskOn: str | None = None
    rotationRegimeStrategyNeutral: str | None = None
    rotationRegimeStrategyRiskOff: str | None = None
    rotationOverlayMode: str | None = None
    rotationOverlayMinTickers: int | None = None
    rotationOverlayConfidenceThreshold: float | None = None
    rotationOverlayWatchlist: list[str] | None = None
    rotationActiveIndex: int | None = None
    rotationLastAt: str | None = None
    rotationActiveStrategy: str | None = None
