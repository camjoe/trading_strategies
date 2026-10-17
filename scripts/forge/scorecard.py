"""Scoring the findings of readiness comments by what became of them.

For each lens (reviewer) it counts the findings it reported and how each ended: fixed, decided by the owner,
or left open. Reactions on a finding's inline comment (a thumbs up or down) are counted beside them. Read-only.
"""

import re
from collections import Counter
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from scripts.forge.findings import Finding, parse_findings

_TAG = re.compile(r"\[([^\[\]]+)\]\s*$")
_LENS_SUFFIX = re.compile(r"\s*(?:\(.*?\)|x\d+)\s*$")
UNTAGGED = "(untagged)"


@dataclass(frozen=True)
class ScoredFinding:
    number: int
    outcome: str
    lenses: tuple[str, ...]
    up: int = 0
    down: int = 0


def lenses_of(finding: Finding) -> tuple[str, ...]:
    """The lens names in the finding's trailing ``[...]`` tag, without model or sample suffixes."""
    match = _TAG.search(finding.text.splitlines()[0]) if finding.text else None
    if match is None:
        return (UNTAGGED,)
    names: list[str] = []
    for part in match.group(1).split(";")[0].split(","):
        name = _LENS_SUFFIX.sub("", part.strip())
        if name and not name.startswith("rated "):
            names.append(name)
    return tuple(dict.fromkeys(names)) or (UNTAGGED,)


def outcome_of(finding: Finding) -> str:
    """``left open``, ``decided``, ``fixed``, or ``closed`` for a closed finding that says neither."""
    if finding.is_open:
        return "left open"
    if not finding.checked:
        return "other"
    first = finding.text.splitlines()[0]
    if "Decided" in first or finding.decided:
        return "decided"
    return "fixed" if "Fixed" in first else "closed"


def score_comment(body: str, reactions: Mapping[int, tuple[int, int]] | None = None) -> list[ScoredFinding]:
    """Every finding of one readiness comment with its outcome, lenses, and reactions."""
    reactions = reactions or {}
    return [
        ScoredFinding(
            finding.number,
            outcome_of(finding),
            lenses_of(finding),
            *reactions.get(finding.number, (0, 0)),
        )
        for finding in parse_findings(body)
    ]


def tally(scored: Collection[ScoredFinding]) -> dict[str, Counter[str]]:
    """Per lens: findings, each outcome, and thumbs up and down. A finding counts for every lens that reported it."""
    rows: dict[str, Counter[str]] = {}
    for finding in scored:
        for lens in finding.lenses:
            row = rows.setdefault(lens, Counter())
            row["findings"] += 1
            row[finding.outcome] += 1
            row["up"] += finding.up
            row["down"] += finding.down
    return rows


def render_table(rows: Mapping[str, Counter[str]]) -> str:
    """A fixed-width table, busiest lens first."""
    header = f"{'lens':24} {'found':>6} {'fixed':>6} {'decided':>8} {'left open':>10} {'up':>4} {'down':>5}"
    lines = [header]
    for lens, row in sorted(rows.items(), key=lambda item: (-item[1]["findings"], item[0])):
        lines.append(
            f"{lens:24} {row['findings']:6} {row['fixed']:6} {row['decided']:8} {row['left open']:10} "
            f"{row['up']:4} {row['down']:5}"
        )
    return "\n".join(lines)
