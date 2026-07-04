from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_int, row_expect_str, row_str


@dataclass(frozen=True, slots=True)
class StrategyRecord:
    """Persisted strategies row: a code primitive + its knobs (D5)."""

    id: int
    strategy_key: str
    primitive: str
    params_json: str
    style: str
    required_features: str | None
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
            style=row_expect_str(values, "style"),
            required_features=row_str(values, "required_features"),
            description=row_str(values, "description"),
            status=row_expect_str(values, "status"),
            enabled=row_expect_int(values, "enabled"),
            created_at=row_expect_str(values, "created_at"),
            updated_at=row_expect_str(values, "updated_at"),
        )
