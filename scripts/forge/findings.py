"""Reading the verdict and findings out of a readiness comment."""

import re
from dataclasses import dataclass

_TITLE = re.compile(r"^## PR readiness: (READY|NOT READY)\s*$", re.MULTILINE)
_ITEM = re.compile(r"^- \[( |x)\] \*\*(\d+)\.")
_STATUS = re.compile(r"^\s*\*(?:Fix attempted|Not fixed|Left): ")
_DECISION = re.compile(r"^\s*\*Decision: ")
_TIER_HEADINGS = (("Blockers", "blocker"), ("Concerns", "concern"), ("Notes", "note"), ("Closed", "closed"))


@dataclass(frozen=True)
class Finding:
    number: int
    tier: str
    checked: bool
    has_status_line: bool
    decided: bool

    @property
    def is_open(self) -> bool:
        return not self.checked and self.tier != "closed"

    @property
    def is_handled(self) -> bool:
        """Whether a fixer or the owner has already recorded something on it."""
        return self.has_status_line or self.decided


def verdict(body: str) -> str | None:
    """``READY`` or ``NOT READY`` from the comment title, or ``None`` when the title is missing."""
    match = _TITLE.search(body)
    return match.group(1) if match else None


def parse_findings(body: str) -> list[Finding]:
    """Every numbered finding in *body*, in order, with the tier of the heading it sits under."""
    findings: list[Finding] = []
    tier = "note"
    current: dict[str, object] | None = None

    def close() -> None:
        if current is not None:
            findings.append(Finding(**current))  # type: ignore[arg-type]

    for line in body.splitlines():
        if line.startswith("#### "):
            close()
            current = None
            tier = next((name for word, name in _TIER_HEADINGS if word in line), tier)
            continue
        item = _ITEM.match(line)
        if item:
            close()
            current = {
                "number": int(item.group(2)),
                "tier": tier,
                "checked": item.group(1) == "x",
                "has_status_line": False,
                "decided": False,
            }
        elif current is not None:
            current["has_status_line"] = bool(current["has_status_line"]) or bool(_STATUS.match(line))
            current["decided"] = bool(current["decided"]) or bool(_DECISION.match(line))
    close()
    return findings


def unhandled_open_findings(body: str) -> list[Finding]:
    """Open findings nobody has recorded anything on: the work a fixer round can still do."""
    return [finding for finding in parse_findings(body) if finding.is_open and not finding.is_handled]


def open_counts(body: str) -> dict[str, int]:
    """Open findings per tier, for a notification that must not carry the findings themselves."""
    counts = {"blocker": 0, "concern": 0, "note": 0}
    for finding in parse_findings(body):
        if finding.is_open and finding.tier in counts:
            counts[finding.tier] += 1
    return counts
