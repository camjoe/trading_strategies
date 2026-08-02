from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_int, row_str


@dataclass(frozen=True, slots=True)
class AccountRecord(Mapping[str, object]):
    """Persisted account row materialized from the database.

    The final account shape (revision 0008): identity, custody, and broker
    connection. Strategy truth is book_strategy_history; goals,
    universes, and execution/option settings are books columns.
    """

    id: int
    name: str
    initial_cash: float
    created_at: str
    benchmark_ticker: str
    descriptive_name: str
    broker_type: str | None = None
    broker_host: str | None = None
    broker_port: int | None = None
    broker_client_id: int | None = None
    live_trading_enabled: int | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> AccountRecord:
        return cls(
            id=row_expect_int(values, "id"),
            name=row_expect_str(values, "name"),
            initial_cash=row_expect_float(values, "initial_cash"),
            created_at=row_expect_str(values, "created_at"),
            benchmark_ticker=row_expect_str(values, "benchmark_ticker"),
            descriptive_name=row_expect_str(values, "descriptive_name"),
            broker_type=row_str(values, "broker_type"),
            broker_host=row_str(values, "broker_host"),
            broker_port=row_int(values, "broker_port"),
            broker_client_id=row_int(values, "broker_client_id"),
            live_trading_enabled=row_int(values, "live_trading_enabled"),
        )

    def __getitem__(self, key: str) -> object:
        if key not in self.__dataclass_fields__:
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.__dataclass_fields__)

    def __len__(self) -> int:
        return len(self.__dataclass_fields__)
