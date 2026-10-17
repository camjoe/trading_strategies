"""Scoring the findings of readiness comments by what became of them.

For each lens (reviewer) it counts the findings it reported and how each ended: fixed, decided by the owner,
or left open. Reactions on a finding's inline comment (a thumbs up or down) are counted beside them. Read-only.
"""

import re
from collections import Counter
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from scripts.forge.base import ForgeError, ScorecardForge
from scripts.forge.findings import Finding, after_title, parse_findings

_TAG = re.compile(r"\[([^\[\]]+)\]\s*$")
_LENS_SUFFIX = re.compile(r"(?:\s*x\d+)+$")
UNTAGGED = "(untagged)"
LENSES = ("Break it", "Operator", "Test skeptic", "Simplifier", "Architecture and conventions", "Orchestrator")
_CANONICAL = {name.lower(): name for name in LENSES} | {"architecture": "Architecture and conventions"}


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
        name = _LENS_SUFFIX.sub("", re.split(r"\s*\(", part.strip().lower())[0]).strip()
        if name in _CANONICAL:
            names.append(_CANONICAL[name])
    return tuple(dict.fromkeys(names)) or (UNTAGGED,)


def outcome_of(finding: Finding) -> str:
    """``left open``, ``decided``, ``fixed``, or ``other``."""
    if finding.is_open:
        return "left open"
    said = after_title(finding.text)
    if finding.checked and (said.startswith("Decided") or finding.decided):
        return "decided"
    if finding.checked and said.startswith("Fixed"):
        return "fixed"
    return "other"


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
    header = (
        f"{'lens':24} {'found':>6} {'fixed':>6} {'decided':>8} {'left open':>10} {'other':>6} {'up':>4} {'down':>5}"
    )
    lines = [header]
    for lens, row in sorted(rows.items(), key=lambda item: (-item[1]["findings"], item[0])):
        lines.append(
            f"{lens:24} {row['findings']:6} {row['fixed']:6} {row['decided']:8} {row['left open']:10} "
            f"{row['other']:6} {row['up']:4} {row['down']:5}"
        )
    return "\n".join(lines)


def collect_scores(
    forge: ScorecardForge, numbers: Collection[int], authors: Collection[str]
) -> tuple[list[ScoredFinding], list[int], dict[int, str]]:
    """The findings of every readable pull request, the numbers scored, and why each unreadable one failed.

    A pull request with no readiness comment is counted as scored and contributes no findings.
    """
    scored: list[ScoredFinding] = []
    read: list[int] = []
    failed: dict[int, str] = {}
    for number in numbers:
        try:
            comment = forge.find_comment(number, authors)
            if comment is not None:
                scored.extend(score_comment(comment.body, forge.finding_reactions(number, authors)))
        except ForgeError as exc:
            failed[number] = str(exc)
        else:
            read.append(number)
    return scored, read, failed
