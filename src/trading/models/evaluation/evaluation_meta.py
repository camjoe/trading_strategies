from __future__ import annotations

from dataclasses import dataclass

from trading.models.evaluation.constants import EVALUATION_ARTIFACT_VERSION, EVALUATION_SOURCE_MODE


@dataclass(frozen=True)
class EvaluationMeta:
    artifact_version: str = EVALUATION_ARTIFACT_VERSION
    source_mode: str = EVALUATION_SOURCE_MODE
    generated_at: str | None = None
