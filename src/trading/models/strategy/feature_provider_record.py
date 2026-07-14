from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_int, row_expect_str, row_str


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
