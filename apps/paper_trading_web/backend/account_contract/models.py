from __future__ import annotations

from dataclasses import dataclass

from trading.models import AccountConfig


@dataclass(frozen=True)
class ApiFieldMapping:
    api_name: str
    storage_name: str


@dataclass(frozen=True)
class AdminCreateAccountCommand:
    name: str
    strategy: str
    initial_cash: float
    benchmark_ticker: str
    config_values: dict[str, object]
    # The profile-shaped `rotation` object (book-owned scheduling, ADR 014).
    rotation_settings: dict[str, object]

    @property
    def config(self) -> AccountConfig:
        return AccountConfig.from_mapping(self.config_values)


@dataclass(frozen=True)
class AccountParamsUpdateCommand:
    strategy: str | None
    config_values: dict[str, object]
    # The profile-shaped `rotation` object (book-owned scheduling, ADR 014).
    rotation_settings: dict[str, object]

    @property
    def config(self) -> AccountConfig:
        return AccountConfig.from_mapping(self.config_values)
