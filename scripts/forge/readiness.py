"""Checks on the text of a readiness comment before it is posted."""

import re
from collections.abc import Collection

from scripts.forge.base import READINESS_MARKER

_PASS_HEADER = re.compile(r"· pass (\d+) ·")
_FORBIDDEN_TEXT = ("/home/runner", "/Users/")
_CREDENTIAL_PATTERNS = (re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"), re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"))


def pass_number(body: str) -> int | None:
    """The pass number in the comment header (``· pass N ·``), or ``None`` when it is not there."""
    match = _PASS_HEADER.search(body)
    return int(match.group(1)) if match else None


def body_problems(body: str, previous_pass: int | None, forbidden: Collection[str] = ()) -> list[str]:
    """Reasons *body* must not be posted; empty when it is fine.

    *previous_pass* is the pass number of the comment being replaced (``None`` on a first pass), so a
    pass must be exactly one more than the last. *forbidden* lists extra literal strings, such as a
    token's value, that must not appear.
    """
    problems: list[str] = []
    if not body.startswith(READINESS_MARKER):
        problems.append("The body does not start with the readiness marker.")
    found = pass_number(body)
    expected = (previous_pass or 0) + 1
    if found != expected:
        problems.append(f"The header should say pass {expected}, but says pass {found}.")
    if any(item and item in body for item in (*_FORBIDDEN_TEXT, *forbidden)):
        problems.append("The body contains a local path or a forbidden string.")
    if any(pattern.search(body) for pattern in _CREDENTIAL_PATTERNS):
        problems.append("The body contains credential-like text.")
    return problems
