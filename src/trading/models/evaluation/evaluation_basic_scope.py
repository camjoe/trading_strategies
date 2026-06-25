from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationBasicScope:
    account_id: int | None = None
    account_name: str | None = None
    descriptive_name: str | None = None
    requested_strategy: str | None = None
    base_strategy: str | None = None
    active_strategy: str | None = None
    benchmark_ticker: str | None = None
    instrument_mode: str | None = None
    rotation_enabled: bool = False
    live_trading_enabled: bool = False
