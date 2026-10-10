"""Checks on the text of a readiness comment before it is posted."""

import re
from collections.abc import Collection

from scripts.forge.base import ForgeError, require_marker

_PASS_HEADER = re.compile(r"^Reviewed .* · pass (\d+) ·", re.MULTILINE)
_PATH_PATTERNS = (
    re.compile(r"/home/runner/[^\s`]"),
    re.compile(r"/Users/[^\s/`]+/"),
    re.compile(r"[A-Za-z]:\\Users\\"),
)
_CREDENTIAL_PATTERNS = (re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"), re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"))


def pass_number(body: str) -> int | None:
    """The pass number in the comment header line (``Reviewed ... · pass N ·``), or ``None`` when absent."""
    match = _PASS_HEADER.search(body)
    return int(match.group(1)) if match else None


def body_problems(body: str, previous_pass: int | None, forbidden: Collection[str] = ()) -> list[str]:
    """Reasons *body* must not be posted; empty when it is fine.

    *previous_pass* is the pass number of the comment being replaced (``None`` on a first pass), so a
    pass must be exactly one more than the last. *forbidden* lists literal strings, such as a token's
    value, that must not appear; an empty entry is an error because it would check nothing.
    """
    problems: list[str] = []
    try:
        require_marker(body)
    except ForgeError as exc:
        problems.append(str(exc))
    found = pass_number(body)
    expected = (previous_pass or 0) + 1
    if found != expected:
        problems.append(f"The header should say pass {expected}, but says pass {found}.")
    if any(not item for item in forbidden):
        problems.append("A forbidden string is empty, so it cannot be checked.")
    elif any(item in body for item in forbidden):
        problems.append("The body contains a forbidden string.")
    if any(pattern.search(body) for pattern in _PATH_PATTERNS):
        problems.append("The body contains a local path.")
    if any(pattern.search(body) for pattern in _CREDENTIAL_PATTERNS):
        problems.append("The body contains credential-like text.")
    return problems
