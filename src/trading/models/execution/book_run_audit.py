from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BookRunAudit:
    """Risk audit accumulated across one book run's stages.

    Carries the gate's per-intent decisions plus any block reasons raised later
    in the run (kill switches, the trade throttle, a broker anomaly), the
    run-wide ``kill_switch_reasons``, and the counts rendered into the persisted
    snapshot's ``summary``. Mutable by design: the runtime fills it in as stages
    complete, then hands the whole thing to the execution-owned persistence.
    """

    risk_decisions: list[dict[str, object]] = field(default_factory=list)
    kill_switch_reasons: list[str] = field(default_factory=list)
    blocked_count: int = 0
    rescaled_count: int = 0
    allowed_count: int = 0
    submitted_count: int = 0

    def record_block(self, reason_code: str, *, book_id: int | None = None) -> None:
        """Append a block decision. ``book_id`` is omitted for run-wide reasons."""
        decision: dict[str, object] = {"action": "block", "reason_code": reason_code}
        if book_id is not None:
            decision["book_id"] = book_id
        self.risk_decisions.append(decision)

    def summary(self) -> dict[str, object]:
        return {
            "submitted_count": self.submitted_count,
            "blocked_count": self.blocked_count,
            "rescaled_count": self.rescaled_count,
            "allowed_count": self.allowed_count,
        }
