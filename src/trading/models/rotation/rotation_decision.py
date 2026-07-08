from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RotationDecision:
    rotation_action: str
    selected_strategy: str
    selected_param_set_id: int | None
    incumbent_strategy: str
    challenger_strategy: str | None
    challenger_param_set_id: int | None
    cooldown_active: bool
    decision_reason: str
    score_components: dict[str, dict[str, float]]
    gate_results: dict[str, object]
