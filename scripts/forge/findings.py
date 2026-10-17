"""Reading the verdict and findings out of a readiness comment."""

import re
from dataclasses import dataclass

_TITLE = re.compile(r"^## PR readiness: (READY|NOT READY)\s*$")
_ITEM = re.compile(r"^- \[( |x)\] \*\*(\d+)\.")
_STATUS = re.compile(r"^\s*\*(?:Fix attempted|Not fixed|Left): ")
_DECISION = re.compile(r"^\s*\*Decision: ")
_TIER_HEADING = re.compile(r"^#### \W*(Blockers|Concerns|Notes|Tests|Closed)\W*(?:\(\d+\)\W*)?$")
_ANY_HEADING = re.compile(r"^#{1,6} ")
_FINDING_TITLE = re.compile(r"^\*\*\d+\..*?[.?!]\*\*\s*")
_TIERS = {"Blockers": "blocker", "Concerns": "concern", "Notes": "note", "Tests": "note", "Closed": "closed"}


@dataclass(frozen=True)
class Finding:
    number: int
    tier: str
    checked: bool
    has_status_line: bool
    decided: bool
    text: str

    @property
    def is_open(self) -> bool:
        return not self.checked and self.tier in ("blocker", "concern", "note")

    @property
    def is_handled(self) -> bool:
        """Whether a fixer or the owner has already recorded something on it."""
        return self.has_status_line or self.decided


def after_title(text: str) -> str:
    """The first line of a finding's *text* without its ``**n. Title.**`` prefix."""
    return _FINDING_TITLE.sub("", text.splitlines()[0]) if text else ""


def verdict(body: str) -> str | None:
    """``READY`` or ``NOT READY`` from the comment title, or ``None`` when the title is missing.

    The title is the first level-two heading.
    """
    heading = next((line for line in body.splitlines() if line.startswith("## ")), "")
    match = _TITLE.match(heading)
    return match.group(1) if match else None


def parse_findings(body: str) -> list[Finding]:
    """Every numbered finding in *body*, in order, with the tier of the heading it sits under.

    Only the five tier headings count (Tests counts as notes); any other heading ends the current tier, so
    what follows it is not treated as open.
    """
    findings: list[Finding] = []
    tier = "other"
    number: int | None = None
    checked = has_status = decided = False
    lines: list[str] = []

    def close() -> None:
        if number is not None:
            findings.append(Finding(number, tier, checked, has_status, decided, "\n".join(lines).rstrip()))

    for line in body.splitlines():
        heading = _TIER_HEADING.match(line)
        if heading or _ANY_HEADING.match(line):
            close()
            number = None
            tier = _TIERS[heading.group(1)] if heading else "other"
            continue
        item = _ITEM.match(line)
        if item:
            close()
            number, checked = int(item.group(2)), item.group(1) == "x"
            has_status = decided = False
            lines = [line[len("- [ ] ") :]]
        elif number is not None:
            has_status = has_status or bool(_STATUS.match(line))
            decided = decided or bool(_DECISION.match(line))
            if line.startswith("  "):
                lines.append(line[2:])
    close()
    return findings


def unhandled_open_findings(body: str) -> list[Finding]:
    """Open findings nobody has recorded anything on: the work a fixer round can still do."""
    return [finding for finding in parse_findings(body) if finding.is_open and not finding.is_handled]


def open_counts(body: str) -> dict[str, int]:
    """Open findings per tier, for a notification that must not carry the findings themselves."""
    counts = {"blocker": 0, "concern": 0, "note": 0}
    for finding in parse_findings(body):
        if finding.is_open:
            counts[finding.tier] += 1
    return counts
