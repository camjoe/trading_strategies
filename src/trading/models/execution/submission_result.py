from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SubmissionResult:
    """Outcome of submitting one book's approved intents through the execution service.

    ``order_ids`` are the clean ``orders`` rows written (one per intent that reached
    the broker). ``kill_switch_reasons`` echoes the gate's reasons plus any
    broker-API anomaly raised mid-loop; a non-empty list means submission halted.
    """

    order_ids: list[int] = field(default_factory=list)
    submitted_count: int = 0
    filled_count: int = 0
    blocked_count: int = 0
    rescaled_count: int = 0
    kill_switch_reasons: list[str] = field(default_factory=list)
