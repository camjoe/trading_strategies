from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RotationDecision:
    rotation_action: str
    selected_strategy: str
    incumbent_strategy: str
    challenger_strategy: str | None
    cooldown_active: bool
    decision_reason: str
    score_components: dict[str, dict[str, float]]
    gate_results: dict[str, object]
