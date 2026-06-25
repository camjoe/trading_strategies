from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_int, row_expect_str, row_str


@dataclass(frozen=True, slots=True)
class StrategyParamSetRecord:
    """Persisted strategy_param_sets row materialized from the database."""

    id: int
    strategy_name: str
    version: str
    params_json: str
    config_version: str | None
    is_active: int
    created_at: str
    updated_at: str
    activated_at: str | None
    deactivated_at: str | None
    notes: str | None

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> StrategyParamSetRecord:
        return cls(
            id=row_expect_int(values, "id"),
            strategy_name=row_expect_str(values, "strategy_name"),
            version=row_expect_str(values, "version"),
            params_json=row_expect_str(values, "params_json"),
            config_version=row_str(values, "config_version"),
            is_active=row_expect_int(values, "is_active"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
            activated_at=row_str(values, "activated_at"),
            deactivated_at=row_str(values, "deactivated_at"),
            notes=row_str(values, "notes"),
        )
