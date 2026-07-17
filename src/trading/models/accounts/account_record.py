from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_float, row_int, row_str


@dataclass(frozen=True, slots=True)
class AccountRecord(Mapping[str, object]):
    """Persisted account row materialized from the database.

    The retired account rotation columns (rotation_*) were dropped in
    revision 0003 — rotation scheduling is book-owned and rotation state
    lives in book_strategy_assignments and rotation_decisions (ADR 014).
    """

    id: int
    name: str
    account_kind: str
    strategy: str
    initial_cash: float
    created_at: str
    benchmark_ticker: str
    descriptive_name: str
    goal_min_return_pct: float | None
    goal_max_return_pct: float | None
    goal_period: str
    broker_type: str | None = None
    broker_host: str | None = None
    broker_port: int | None = None
    broker_client_id: int | None = None
    live_trading_enabled: int | None = None
    trade_universes: str | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> AccountRecord:
        return cls(
            id=row_expect_int(values, "id"),
            name=row_expect_str(values, "name"),
            account_kind=row_expect_str(values, "account_kind"),
            strategy=row_expect_str(values, "strategy"),
            initial_cash=row_expect_float(values, "initial_cash"),
            created_at=row_expect_str(values, "created_at"),
            benchmark_ticker=row_expect_str(values, "benchmark_ticker"),
            descriptive_name=row_expect_str(values, "descriptive_name"),
            goal_min_return_pct=row_float(values, "goal_min_return_pct"),
            goal_max_return_pct=row_float(values, "goal_max_return_pct"),
            goal_period=row_expect_str(values, "goal_period"),
            broker_type=row_str(values, "broker_type"),
            broker_host=row_str(values, "broker_host"),
            broker_port=row_int(values, "broker_port"),
            broker_client_id=row_int(values, "broker_client_id"),
            live_trading_enabled=row_int(values, "live_trading_enabled"),
            trade_universes=row_str(values, "trade_universes"),
        )

    def __getitem__(self, key: str) -> object:
        if key not in self.__dataclass_fields__:
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.__dataclass_fields__)

    def __len__(self) -> int:
        return len(self.__dataclass_fields__)
