"""Scoring the findings of readiness comments by what became of them.

For each lens (reviewer) it counts the findings it reported and how each ended: fixed, decided by the owner,
or left open. Reactions on a finding's inline comment (a thumbs up or down) are counted beside them. Read-only.
"""

import re
from collections import Counter
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field

from scripts.forge.base import ForgeError, PullRequestDetails, ScorecardForge
from scripts.forge.findings import Finding, after_title, parse_findings, verdict
from scripts.forge.readiness import pass_number

_TAG = re.compile(r"\[([^\[\]]+)\]\s*$")
KINDS = ("bug", "safety", "docs", "test", "design", "wording")
_PASS_SEGMENT = re.compile(r"pass (\d+)")
_NEEDS = re.compile(r"→\s*(fix|decision|info):")
_CLOSED_BY = re.compile(r"\(pass (\d+), by (fixer|author|owner)\)")
_LENS_SUFFIX = re.compile(r"(?:\s*x\d+)+$")
UNTAGGED = "(untagged)"
LENSES = ("Break it", "Operator", "Test skeptic", "Simplifier", "Architecture and conventions", "Orchestrator")
_CANONICAL = {name.lower(): name for name in LENSES} | {"architecture": "Architecture and conventions"}
_ANCHOR = re.compile(r"`([^`\s:]+):(\d+)(?:-\d+)?`")
_FIXED_IN = re.compile(r"Fixed in (?:`([^`]+)`|([0-9a-fA-F]{7,40})\b)")
_LOWERED = re.compile(r"lowered to NOTE because (.+)$")
_TITLE_TEXT = re.compile(r"^\*\*\d+\.\s*(.*?)\.?\*\*")
_DOC_SUFFIXES = (".md", ".rst")
_CONFIG_SUFFIXES = (".json", ".yml", ".yaml", ".toml", ".ini", ".cfg")
_AGENT_FILES = ("agents.md", "claude.md")


def area_of(path: str) -> str:
    """A coarse kind of file: ``tests``, ``ci``, ``agent`` (agent skills and instructions), ``docs``, ``config``, or ``code``."""
    parts = path.lower().split("/")
    name = parts[-1]
    if any(part in ("test", "tests") for part in parts[:-1]) or name.startswith("test_") or name.endswith("_test.py"):
        return "tests"
    if parts[0] == ".github":
        return "ci"
    if parts[0] in (".ai", ".claude") or name in _AGENT_FILES:
        return "agent"
    if parts[0] == "docs" or name.endswith(_DOC_SUFFIXES):
        return "docs"
    if name.endswith(_CONFIG_SUFFIXES):
        return "config"
    return "code"


@dataclass(frozen=True)
class ScoredFinding:
    number: int
    outcome: str
    lenses: tuple[str, ...]
    tier: str = "note"
    up: int = 0
    down: int = 0
    title: str = ""
    path: str | None = None
    line: int | None = None
    area: str | None = None
    fixed_in: str | None = None
    lowered: str | None = None
    text: str = ""
    kind: str | None = None
    needs: str | None = None
    opened_pass: int | None = None
    closed_pass: int | None = None
    closed_by: str | None = None


@dataclass(frozen=True)
class PullRequestScore:
    """The scored findings of one pull request's readiness comment, with its pass count and verdict."""

    findings: list[ScoredFinding]
    passes: int | None
    verdict: str | None
    details: PullRequestDetails | None = None
    file_areas: dict[str, str] = field(default_factory=dict)


def _tag_parts(finding: Finding) -> tuple[str, str | None, int | None]:
    """The reviewers text, the kind, and the opening pass from the trailing ``[reviewers · kind · pass n]`` tag."""
    match = _TAG.search(finding.text.splitlines()[0]) if finding.text else None
    if match is None:
        return "", None, None
    segments = [segment.strip() for segment in match.group(1).split(" · ")]
    kind = next((segment for segment in segments[1:] if segment in KINDS), None)
    opened = next((int(m.group(1)) for segment in segments[1:] if (m := _PASS_SEGMENT.fullmatch(segment))), None)
    return segments[0], kind, opened


def lenses_of(finding: Finding) -> tuple[str, ...]:
    """The lens names in the finding's trailing ``[...]`` tag, without model or sample suffixes."""
    reviewers, _, _ = _tag_parts(finding)
    if not reviewers:
        return (UNTAGGED,)
    names: list[str] = []
    for part in reviewers.split(";")[0].split(","):
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
    scored = {
        finding.number: _scored(finding, *reactions.get(finding.number, (0, 0))) for finding in parse_findings(body)
    }
    return list(scored.values())


def _scored(finding: Finding, up: int, down: int) -> ScoredFinding:
    first = finding.text.splitlines()[0] if finding.text else ""
    anchor = _ANCHOR.search(first)
    title = _TITLE_TEXT.match(first)
    said = after_title(finding.text)
    fixed = _FIXED_IN.search(said)
    reviewers, kind, opened = _tag_parts(finding)
    lowered = _LOWERED.search(reviewers)
    needs = _NEEDS.search(first)
    closed = _CLOSED_BY.search(said)
    path = anchor.group(1) if anchor else None
    return ScoredFinding(
        finding.number,
        outcome_of(finding),
        lenses_of(finding),
        finding.tier,
        up,
        down,
        title.group(1) if title else "",
        path,
        int(anchor.group(2)) if anchor else None,
        area_of(path) if path else None,
        (fixed.group(1) or fixed.group(2)) if fixed else None,
        lowered.group(1).strip() if lowered else None,
        finding.text,
        kind,
        needs.group(1) if needs else None,
        opened,
        int(closed.group(1)) if closed else None,
        closed.group(2) if closed else None,
    )


def score_pull_request(
    body: str, reactions: Mapping[int, tuple[int, int]] | None = None, details: PullRequestDetails | None = None
) -> PullRequestScore:
    """The findings of one readiness comment with its pass number, verdict, and, when given, pull request details."""
    file_areas = {path: area_of(path) for path in details.files} if details else {}
    return PullRequestScore(score_comment(body, reactions), pass_number(body), verdict(body), details, file_areas)


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
    forge: ScorecardForge, numbers: Collection[int], authors: Collection[str], with_details: bool = False
) -> tuple[dict[int, PullRequestScore], list[int], dict[int, str]]:
    """The score of every pull request that has a readiness comment, the numbers read, and why each unreadable one failed.

    A pull request with no readiness comment counts as read and has no score.
    """
    scores: dict[int, PullRequestScore] = {}
    read: list[int] = []
    failed: dict[int, str] = {}
    for number in numbers:
        try:
            comment = forge.find_comment(number, authors)
            if comment is not None:
                details = forge.pull_request_details(number) if with_details else None
                scores[number] = score_pull_request(comment.body, forge.finding_reactions(number, authors), details)
        except ForgeError as exc:
            failed[number] = str(exc)
        else:
            read.append(number)
    return scores, read, failed


HUMAN_ENDINGS = ("fixer", "author", "owner", "left open", "(not recorded)")
HUMAN_NEEDS = ("fix", "decision", "info", "(not recorded)")


def render_human_table(counts: Mapping[tuple[str, str], int]) -> str:
    """Rows are what the reviewer predicted the finding needed; columns are how it ended."""
    header = f"{'predicted':16}" + "".join(f"{ending:>16}" for ending in HUMAN_ENDINGS)
    lines = [header]
    for need in HUMAN_NEEDS:
        lines.append(f"{need:16}" + "".join(f"{counts.get((need, ending), 0):16}" for ending in HUMAN_ENDINGS))
    return "\n".join(lines)
