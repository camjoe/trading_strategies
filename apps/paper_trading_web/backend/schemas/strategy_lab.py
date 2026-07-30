from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from trading.services.profiles.source import DEFAULT_TICKERS_FILE

# The optimizer route runs its sweep synchronously, so the request is open for the
# whole run. A sweep costs roughly `candidates x windows` simulations, and one
# simulation measured ~0.74s on the default 12-ticker universe
# (`python -m scripts.benchmark_sweep`), rising with universe size. At the default
# 24-month/1-month geometry that is ~13 windows, so a budget of 32 bounds a UI-
# triggered sweep at around five minutes and a budget of 256 would have allowed
# forty. The ceiling is a property of the synchronous route, not of the optimizer:
# the CLI runs the same sweep unbounded because nothing is waiting on a socket.
MAX_CANDIDATE_BUDGET = 32

# Comfortably above the form's default 2x2 grid, low enough that a larger search
# is a deliberate edit rather than an accident.
DEFAULT_CANDIDATE_BUDGET = 16


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
    candidateBudget: int = Field(default=DEFAULT_CANDIDATE_BUDGET, gt=0, le=MAX_CANDIDATE_BUDGET)
    warmupMonths: int = Field(default=6, ge=0)
