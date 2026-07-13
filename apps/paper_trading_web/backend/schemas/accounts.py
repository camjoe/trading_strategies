from __future__ import annotations

from pydantic import BaseModel

from .admin import RotationSettingsPayload


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
    rotation: RotationSettingsPayload | None = None
