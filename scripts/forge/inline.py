"""Keeping one review comment per open blocker or concern on the line it names.

The readiness comment stays the full record. This module copies each open blocker and concern onto its
changed line, edits the copy when the finding changes, and, when the finding closes, edits it to the closed
text, replies once, and tries to resolve the thread.
"""

import re
from collections.abc import Collection

from scripts.forge.base import ForgeError, InlineComment, InlineForge, finding_marker
from scripts.forge.findings import Finding, after_title, parse_findings

_ANCHOR = re.compile(r"`([^`\s:]+):(\d+)(?:-\d+)?`")
_INLINE_TIERS = ("blocker", "concern")
_CLOSING = re.compile(r"(Fixed in (?:`[^`]+`|[^\s`:.,]+)|Decided\b)")


def anchor_of(finding: Finding) -> tuple[str, int] | None:
    """The ``path:line`` a finding names in its first line, or ``None`` for a finding about no one line."""
    match = _ANCHOR.search(finding.text.splitlines()[0]) if finding.text else None
    return (match.group(1), int(match.group(2))) if match else None


def render(finding: Finding) -> str:
    """The comment text for *finding*, starting with its marker."""
    return f"{finding_marker(finding.number)}\n{finding.text}"


def _closing(number: int, known: Finding | None) -> tuple[str, str | None]:
    """The text a comment keeps once its finding needs no comment on that line, and the reply that announces a close."""
    marker = finding_marker(number)
    if known is None:
        return f"{marker}\nNo longer in the readiness comment.", None
    if known.checked:
        said = _CLOSING.match(after_title(known.text))
        phrase = said.group(1).rstrip(".") if said else "Closed"
        return f"{marker}\n✓ {known.text}", f"{marker}\n✓ {phrase}."
    if known.is_open and known.tier in _INLINE_TIERS:
        return f"{marker}\nThe finding is no longer on a changed line: see the readiness comment.", None
    if known.is_open:
        return f"{marker}\nLowered to a note: see the readiness comment.", None
    return f"{marker}\nSee the readiness comment.", None


def sync_inline_comments(
    forge: InlineForge, number: int, head_sha: str, body: str, authors: Collection[str]
) -> dict[str, int]:
    """Create, edit, reply to, and resolve finding comments so they match *body*; returns what it did.

    A closing thread gets one reply, to its newest comment and only when it has no reply yet; a refused reply, a
    refused edit, and a thread that cannot be resolved are counted and the sync goes on.
    """
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
        owner = comment.finding_number
        if owner is None:
            continue
        if comment.resolved:
            resolved_places.add((owner, comment.path, comment.line))
        else:
            open_threads.setdefault(owner, []).append(comment)

    counts = {
        "created": 0,
        "edited": 0,
        "resolved": 0,
        "skipped": 0,
        "unresolved": 0,
        "reply_failed": 0,
        "edit_failed": 0,
    }

    def close(comment: InlineComment, text: str, reply: str | None = None) -> None:
        if reply is not None and comment.reply_count == 0:
            try:
                forge.reply_to_inline_comment(number, comment.id, reply)
            except ForgeError:
                counts["reply_failed"] += 1
        if comment.body != text:
            try:
                forge.edit_inline_comment(comment.id, text)
            except ForgeError:
                counts["edit_failed"] += 1
        try:
            forge.resolve_thread(comment.thread_id)
        except ForgeError:
            counts["unresolved"] += 1
        else:
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
            close(comment, f"{finding_marker(n)}\n{reason}")
        if current is not None:
            if current.body != text:
                forge.edit_inline_comment(current.id, text)
                counts["edited"] += 1
        elif (n, path, line) not in resolved_places:
            forge.create_inline_comment(number, head_sha, path, line, text)
            counts["created"] += 1

    for n, comments in open_threads.items():
        text, reply = _closing(n, findings.get(n))
        for position, comment in enumerate(sorted(comments, key=lambda c: c.id, reverse=True)):
            close(comment, text, reply if position == 0 else None)
    return counts
