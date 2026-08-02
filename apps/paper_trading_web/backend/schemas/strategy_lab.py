from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from trading.services.profiles.source import DEFAULT_TICKERS_FILE

# The optimizer route runs its sweep synchronously, so the request is open for the
# whole run. A sweep costs roughly `candidates x windows` simulations; at the
# default 24-month/1-month geometry that is ~13 windows.
#
# Re-measured after indicators moved out of the per-bar path
# (`python -m scripts.benchmark_sweep`): ~42ms per simulation on the default
# 12-ticker universe and ~167ms on a 52-ticker one, down from ~740ms. A budget of
# 128 is ~1,690 simulations — about 70 seconds on the default universe and under
# five minutes on the wide one, which is the case a ceiling exists to bound. The
# previous 32 was calibrated against the old per-simulation cost and had become
# a limit on research rather than a guard.
#
# The ceiling belongs to the synchronous route, not to the optimizer: the CLI
# runs the same sweep unbounded because nothing is waiting on a socket.
MAX_CANDIDATE_BUDGET = 128

# Covers the grids most searches actually use (up to 32 points) without editing
# the field, while leaving a larger search a deliberate act.
DEFAULT_CANDIDATE_BUDGET = 32


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
