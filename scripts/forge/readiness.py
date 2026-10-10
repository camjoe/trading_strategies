"""Checks on the text of a readiness comment before it is posted."""

import difflib
import re
from collections.abc import Collection

from scripts.forge.base import ForgeError, require_marker

_PASS_HEADER = re.compile(r"^Reviewed .* · pass (\d+) ·", re.MULTILINE)
_PATH_PATTERNS = (
    re.compile(r"/home/runner/[^\s`]"),
    re.compile(r"/Users/[^\s/`]+"),
    re.compile(r"[A-Za-z]:\\Users\\"),
)
_FIXER_LINE = re.compile(r"^ {0,3}\*(Fix attempted|Not fixed|Left): ([A-Za-z0-9 ,.;()'_-]{1,300})\*\s*$")
_AUTOLINK = re.compile(r"www\.", re.IGNORECASE)
_CREDENTIAL_PATTERNS = (re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"), re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"))


def pass_number(body: str) -> int | None:
    """The pass number in the comment header line (``Reviewed ... · pass N ·``), or ``None`` when absent."""
    match = _PASS_HEADER.search(body)
    return int(match.group(1)) if match else None


def body_problems(
    body: str, previous_pass: int | None, forbidden: Collection[str] = (), same_pass: bool = False
) -> list[str]:
    """Reasons *body* must not be posted; empty when it is fine.

    *previous_pass* is the pass number of the comment being replaced (``None`` on a first pass), so a
    pass must be exactly one more than the last, or equal to it when *same_pass* is set (an edit of the
    same pass). *forbidden* lists literal strings, such as a token's value, that must not appear; an
    empty entry is an error because it would check nothing.
    """
    problems: list[str] = []
    try:
        require_marker(body)
    except ForgeError as exc:
        problems.append(str(exc))
    found = pass_number(body)
    expected = (previous_pass or 0) + (0 if same_pass else 1)
    if found != expected:
        problems.append(f"The header should say pass {expected}, but says pass {found}.")
    if any(not item for item in forbidden):
        problems.append("A forbidden string is not set or empty, so it cannot be checked.")
    elif any(item in body for item in forbidden):
        problems.append("The body contains a forbidden string.")
    if any(pattern.search(body) for pattern in _PATH_PATTERNS):
        problems.append("The body contains a local path.")
    if any(pattern.search(body) for pattern in _CREDENTIAL_PATTERNS):
        problems.append("The body contains credential-like text.")
    return problems


def _is_status_line(line: str) -> bool:
    match = _FIXER_LINE.match(line)
    return match is not None and not _AUTOLINK.search(match.group(2))


def fixer_edit_problems(old: str, new: str) -> list[str]:
    """Reasons *new* is not a fixer's edit of *old*: it may only add status lines and blank lines.

    A status line is ``*Fix attempted: ...*``, ``*Not fixed: ...*``, or ``*Left: ...*`` with plain text.
    Every existing line must survive unchanged, so an earlier status line stays as evidence. Anything
    else, such as a finding's text or a ticked box, is a problem.
    """
    old_lines, new_lines = old.splitlines(), new.splitlines()
    problems: list[str] = []
    for tag, _, _, new_start, new_end in difflib.SequenceMatcher(
        None, old_lines, new_lines, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            continue
        added = new_lines[new_start:new_end]
        if tag != "insert" or any(line.strip() and not _is_status_line(line) for line in added):
            problems.append(
                f"Line {new_start + 1}: only Fix attempted, Not fixed, and Left lines may be added; existing lines stay."
            )
    return problems
