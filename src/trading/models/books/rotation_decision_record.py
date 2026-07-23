from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from common.coercion import row_expect_int, row_expect_str, row_int, row_str


@dataclass(frozen=True, slots=True)
class RotationDecisionRecord:
    """Persisted rotation_decisions row materialized from the database.

    Carries the stored strategy-id FKs alongside the catalog-resolved strategy
    labels (``incumbent_strategy``/``challenger_strategy``/``selected_strategy``)
    joined in by the repository's labeled-row read queries, so consumers read
    strategy keys directly without re-resolving.
    """

    id: int
    book_id: int
    decision_time: str
    incumbent_strategy_id: int | None
    challenger_strategy_id: int | None
    selected_strategy_id: int | None
    rotation_action: str
    cooldown_active: int
    score_components_json: str
    gate_results_json: str
    decision_reason: str | None
    config_version: str | None
    created_at: str
    incumbent_strategy: str | None
    challenger_strategy: str | None
    selected_strategy: str | None

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> RotationDecisionRecord:
        return cls(
            id=row_expect_int(values, "id"),
            book_id=row_expect_int(values, "book_id"),
            decision_time=row_expect_str(values, "decision_time"),
            incumbent_strategy_id=row_int(values, "incumbent_strategy_id"),
            challenger_strategy_id=row_int(values, "challenger_strategy_id"),
            selected_strategy_id=row_int(values, "selected_strategy_id"),
            rotation_action=row_expect_str(values, "rotation_action"),
            cooldown_active=row_expect_int(values, "cooldown_active"),
            score_components_json=row_expect_str(values, "score_components_json"),
            gate_results_json=row_expect_str(values, "gate_results_json"),
            decision_reason=row_str(values, "decision_reason"),
            config_version=row_str(values, "config_version"),
            created_at=row_expect_str(values, "created_at"),
            incumbent_strategy=row_str(values, "incumbent_strategy"),
            challenger_strategy=row_str(values, "challenger_strategy"),
            selected_strategy=row_str(values, "selected_strategy"),
        )
