from __future__ import annotations

from pydantic import BaseModel

from .admin import RotationSettingsPayload


class AccountParamsRequest(BaseModel):
    strategy: str | None = None
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
    optionProfitTakePct: float | None = None
    optionMaxLossPct: float | None = None
    rotation: RotationSettingsPayload | None = None


class RotationPolicyRequest(BaseModel):
    minTradesInWindow: int | None = None
    outperformanceThresholdBps: float | None = None
    cooldownDays: int | None = None
    riskAdjustedReturnWeight: float | None = None
    stabilityWeight: float | None = None
    drawdownPenaltyWeight: float | None = None
    regimeFitWeight: float | None = None


class BookParamsRequest(AccountParamsRequest):
    tradeUniverses: list[str] | None = None
    maxTradesPerRun: int | None = None
    rotationPolicy: RotationPolicyRequest | None = None
