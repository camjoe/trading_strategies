"""Pydantic request schemas for the paper-trading UI backend.

Schemas defined here:

- ``BacktestBaseRequest`` / ``BacktestRunRequest`` / ``WalkForwardRunRequest`` /
  ``BacktestPreflightRequest`` — backtest and walk-forward job configuration.
- ``AdminCreateAccountRequest`` — full account creation payload (all configurable
  fields including options, rotation, and goal parameters).
- ``AdminDeleteAccountRequest`` — account deletion with a confirmation flag.
- ``AccountParamsRequest`` — partial update of mutable account config and
  rotation fields
  fields for ``PATCH /api/accounts/{name}/params``.  All fields are optional;
  omitted fields are left unchanged.
- ``ManualTradeRequest`` — manual trade injection for
  ``POST /api/accounts/{name}/trades``.
- ``FeatureSignalsRequest`` — ticker lookup for
  ``POST /api/features/signals``.
"""
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
    descriptiveName: str | None = None
    riskPolicy: str | None = None
    stopLossPct: float | None = None
    takeProfitPct: float | None = None
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
    rotationLookbackDays: int | None = None
    rotationSchedule: list[str] | None = None
    rotationActiveIndex: int | None = None
    rotationLastAt: str | None = None
    rotationActiveStrategy: str | None = None


class ManualTradeRequest(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    qty: float = Field(gt=0)
    price: float = Field(gt=0)
    fee: float = Field(default=0.0, ge=0)


class FeatureSignalsRequest(BaseModel):
    ticker: str = Field(min_length=1)
