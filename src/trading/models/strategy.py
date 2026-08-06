"""Strategy-catalog data contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_int, row_expect_str, row_str


@dataclass(frozen=True, slots=True)
class StrategyRecord:
    """Persisted strategies row: a code primitive + its knobs."""

    id: int
    strategy_key: str
    primitive: str
    params_json: str
    description: str | None
    status: str
    enabled: int
    created_at: str
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> StrategyRecord:
        return cls(
            id=row_expect_int(values, "id"),
            strategy_key=row_expect_str(values, "strategy_key"),
            primitive=row_expect_str(values, "primitive"),
            params_json=row_expect_str(values, "params_json"),
            description=row_str(values, "description"),
            status=row_expect_str(values, "status"),
            enabled=row_expect_int(values, "enabled"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )


@dataclass(frozen=True, slots=True)
class FeatureProviderRecord:
    """Persisted feature_providers row materialized from the database."""

    id: int
    provider_key: str
    enabled: int
    config_json: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> FeatureProviderRecord:
        return cls(
            id=row_expect_int(values, "id"),
            provider_key=row_expect_str(values, "provider_key"),
            enabled=row_expect_int(values, "enabled"),
            config_json=row_str(values, "config_json"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )
