"""Keeping one review comment per open blocker or concern on the line it names.

The readiness comment stays the full record. This module copies each open blocker and concern onto its
changed line, edits the copy when the finding changes, and resolves it when the finding closes.
"""

import re
from collections.abc import Collection

from scripts.forge.base import InlineComment, InlineForge, finding_marker
from scripts.forge.findings import Finding, parse_findings

_ANCHOR = re.compile(r"`([^`\s:]+):(\d+)(?:-\d+)?`")
_INLINE_TIERS = ("blocker", "concern")


def anchor_of(finding: Finding) -> tuple[str, int] | None:
    """The ``path:line`` a finding names in its first line, or ``None`` for a finding about no one line."""
    match = _ANCHOR.search(finding.text.splitlines()[0]) if finding.text else None
    return (match.group(1), int(match.group(2))) if match else None


def render(finding: Finding) -> str:
    """The comment text for *finding*, starting with its marker."""
    return f"{finding_marker(finding.number)}\n{finding.text}"


def _closing_text(number: int, known: Finding | None) -> str:
    """What a comment says once its finding no longer needs a comment on that line."""
    marker = finding_marker(number)
    if known is None:
        return f"{marker}\nNo longer in the readiness comment."
    if known.checked:
        return f"{marker}\n✓ {known.text}"
    if known.is_open and known.tier in _INLINE_TIERS:
        return f"{marker}\nThe finding is no longer on a changed line: see the readiness comment."
    if known.is_open:
        return f"{marker}\nLowered to a note: see the readiness comment."
    return f"{marker}\nSee the readiness comment."


def sync_inline_comments(
    forge: InlineForge, number: int, head_sha: str, body: str, authors: Collection[str]
) -> dict[str, int]:
    """Create, edit, and resolve finding comments so they match *body*; returns what it did."""
    findings = {finding.number: finding for finding in parse_findings(body)}
    wanted: dict[int, tuple[Finding, tuple[str, int]]] = {}
    for n, finding in findings.items():
        anchor = anchor_of(finding)
        if finding.is_open and finding.tier in _INLINE_TIERS and anchor is not None:
            wanted[n] = (finding, anchor)
    on_diff = forge.diff_lines(number)
    open_threads: dict[int, list[InlineComment]] = {}
    resolved_places: set[tuple[int, str, int | None]] = set()
    for comment in forge.inline_comments(number, authors):
        n = comment.finding_number
        if n is None:
            continue
        if comment.resolved:
            resolved_places.add((n, comment.path, comment.line))
        else:
            open_threads.setdefault(n, []).append(comment)

    counts = {"created": 0, "edited": 0, "resolved": 0, "skipped": 0}

    def resolve(comment: InlineComment, text: str) -> None:
        if comment.body != text:
            forge.edit_inline_comment(comment.id, text)
        forge.resolve_thread(comment.thread_id)
        counts["resolved"] += 1

    for n, (finding, (path, line)) in wanted.items():
        if line not in on_diff.get(path, frozenset()):
            counts["skipped"] += 1
            continue
        text = render(finding)
        threads = open_threads.pop(n, [])
        current = next((c for c in threads if not c.outdated and (c.path, c.line) == (path, line)), None)
        for comment in threads:
            if comment is current:
                continue
            if comment.outdated:
                reason = "Replaced: the code under this comment changed. See the new comment."
            elif (comment.path, comment.line) == (path, line):
                reason = "Duplicate of another comment on this finding."
            else:
                reason = f"Moved: the finding now sits on {path}:{line}."
            resolve(comment, f"{finding_marker(n)}\n{reason}")
        if current is not None:
            if current.body != text:
                forge.edit_inline_comment(current.id, text)
                counts["edited"] += 1
        elif (n, path, line) not in resolved_places:
            forge.create_inline_comment(number, head_sha, path, line, text)
            counts["created"] += 1

    for n, comments in open_threads.items():
        for comment in comments:
            resolve(comment, _closing_text(n, findings.get(n)))
    return counts
