from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from trading.services.profiles.source import DEFAULT_TICKERS_FILE


class CreateStrategyVariantRequest(BaseModel):
    strategyKey: str
    primitive: str
    params: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None


class ConfigureStrategyRequest(BaseModel):
    params: dict[str, Any] | None = None
    enabled: bool | None = None


class PromoteOptimizationRequest(BaseModel):
    strategyKey: str
    freeze: bool = True


class RunOptimizationRequest(BaseModel):
    account: str
    strategy: str
    searchSpace: dict[str, list[Any]]
    tickersFile: str = DEFAULT_TICKERS_FILE
    universeHistoryDir: str | None = None
    start: str | None = None
    end: str | None = None
    lookbackMonths: int | None = Field(default=None, gt=0)
    slippageBps: float = 5.0
    fee: float = 0.0
    allowApproximateLeaps: bool = False
    trainMonths: int = Field(default=12, gt=0)
    testMonths: int = Field(default=1, gt=0)
    stepMonths: int = Field(default=1, gt=0)
    holdoutMonths: int = Field(default=6, ge=0)
    candidateBudget: int = Field(default=256, gt=0, le=2048)
    warmupMonths: int = Field(default=6, ge=0)
