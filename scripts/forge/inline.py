"""Keeping one review comment per open blocker or concern on the line it names.

The readiness comment stays the full record. This module copies each open blocker and concern onto its
changed line, edits the copy when the finding changes, and resolves it when the finding closes.
"""

import re
from collections.abc import Collection

from scripts.forge.base import FINDING_MARKER, InlineComment, InlineForge
from scripts.forge.findings import Finding, parse_findings

_ANCHOR = re.compile(r"`([^`\s:]+):(\d+)(?:-\d+)?`")
_INLINE_TIERS = ("blocker", "concern")


def anchor_of(finding: Finding) -> tuple[str, int] | None:
    """The ``path:line`` a finding names in its first line, or ``None`` for a finding about no one line."""
    match = _ANCHOR.search(finding.text.splitlines()[0]) if finding.text else None
    return (match.group(1), int(match.group(2))) if match else None


def render(finding: Finding) -> str:
    """The comment text for *finding*, starting with its marker."""
    return f"{FINDING_MARKER.format(number=finding.number)}\n{finding.text}"


def render_closed(finding: Finding) -> str:
    """The text a resolved comment keeps: the marker, a tick, and what the readiness comment says closed it."""
    return f"{FINDING_MARKER.format(number=finding.number)}\n✓ {finding.text}"


def sync_inline_comments(
    forge: InlineForge, number: int, head_sha: str, body: str, authors: Collection[str]
) -> dict[str, int]:
    """Create, edit, and resolve finding comments so they match *body*; returns what it did."""
    findings = {finding.number: finding for finding in parse_findings(body)}
    wanted = {
        n: finding
        for n, finding in findings.items()
        if finding.is_open and finding.tier in _INLINE_TIERS and anchor_of(finding) is not None
    }
    on_diff = forge.diff_lines(number)
    existing: dict[int, list[InlineComment]] = {}
    for comment in forge.inline_comments(number, authors):
        if not comment.resolved and comment.finding_number is not None:
            existing.setdefault(comment.finding_number, []).append(comment)

    counts = {"created": 0, "edited": 0, "resolved": 0, "skipped": 0}

    def resolve(comment: InlineComment, text: str) -> None:
        if comment.body != text:
            forge.edit_inline_comment(comment.id, text)
        forge.resolve_thread(comment.thread_id)
        counts["resolved"] += 1

    for n, finding in wanted.items():
        path, line = anchor = anchor_of(finding) or ("", 0)
        text = render(finding)
        if line not in on_diff.get(path, frozenset()):
            counts["skipped"] += 1
            continue
        current = next(
            (c for c in existing.get(n, []) if not c.outdated and (c.path, c.line) == anchor),
            None,
        )
        for comment in existing.pop(n, []):
            if comment is not current:
                resolve(comment, f"{FINDING_MARKER.format(number=n)}\nMoved: the finding now sits on {path}:{line}.")
        if current is None:
            forge.create_inline_comment(number, head_sha, path, line, text)
            counts["created"] += 1
        elif current.body != text:
            forge.edit_inline_comment(current.id, text)
            counts["edited"] += 1

    for n, comments in existing.items():
        known = findings.get(n)
        if known is None:
            closed = f"{FINDING_MARKER.format(number=n)}\n✓ No longer in the readiness comment."
        elif known.is_open and known.tier in _INLINE_TIERS:
            closed = f"{FINDING_MARKER.format(number=n)}\nThe finding is no longer on a changed line: see the readiness comment."
        elif known.is_open:
            closed = f"{FINDING_MARKER.format(number=n)}\nLowered to a note: see the readiness comment."
        else:
            closed = render_closed(known)
        for comment in comments:
            resolve(comment, closed)
    return counts
