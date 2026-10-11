"""Checks on the text of a readiness comment, and of agent-written text, before it is published."""

import difflib
import re
from collections.abc import Collection

from scripts.forge.base import ForgeError, require_marker

_PASS_HEADER = re.compile(r"^Reviewed .* · pass (\d+) ·", re.MULTILINE)
_PATH_PATTERNS = (
    re.compile(r"/home/runner/[^\s`]"),
    re.compile(r"/Users/[^\s/`]+"),
    re.compile(r"(?<![\w./-])/home/[^\s/`]+/[^\s`]"),
    re.compile(r"(?<![\w.])~/[^\s`]"),
    re.compile(r"[A-Za-z]:[\\/]Users[\\/]"),
)
_ACCOUNT_ID = re.compile(r"\b(?:DU|DF|U|F)\d{6,9}\b")
MAX_ADDED_STATUS_LINES = 12
_FIXER_LINE = re.compile(r"^ {0,3}\*(Fix attempted|Not fixed|Left): ([A-Za-z0-9 ,.;()'_-]{1,300})\*\s*$")
_AUTOLINK = re.compile(r"www\.", re.IGNORECASE)
_CREDENTIAL_PATTERNS = (re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"), re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"))

_CODE_SPANS = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)
_PUBLISH_PATTERNS = (
    (re.compile(r"/home/[^\s/`]+|/Users/[^\s/`]+|[A-Za-z]:\\"), "a local path"),
    (re.compile(r"\blocal/"), "a reference to the private local folder"),
)
_RENDERED_PATTERNS = (
    (re.compile(r"(?<!\w)@\w"), "a mention"),
    (re.compile(r"<[A-Za-z!/]"), "HTML"),
    (re.compile(r"!\[|\]\("), "an image or link"),
    (re.compile(r"https?://|www\.", re.IGNORECASE), "a URL"),
)


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
    return problems + leak_problems(body, forbidden)


def leak_problems(text: str, forbidden: Collection[str] = ()) -> list[str]:
    """Reasons *text* is not safe to publish: a forbidden string, a local path, or credential-like text."""
    problems: list[str] = []
    if any(not item for item in forbidden):
        problems.append("A forbidden string is not set or empty, so it cannot be checked.")
    elif any(item in text for item in forbidden):
        problems.append("The body contains a forbidden string.")
    if any(pattern.search(text) for pattern in _PATH_PATTERNS):
        problems.append("The body contains a local path.")
    if any(pattern.search(text) for pattern in _CREDENTIAL_PATTERNS):
        problems.append("The body contains credential-like text.")
    if _ACCOUNT_ID.search(text):
        problems.append("The body contains text shaped like a broker account id.")
    return problems


def publish_problems(text: str) -> list[str]:
    """Reasons agent-written *text* must not go into a public description; empty when it can.

    Paths, account-id shapes, and the private folder are refused anywhere. Mentions, HTML, links, and URLs
    are refused outside code, where GitHub would render or act on them.
    """
    problems = leak_problems(text)
    problems += [f"The text contains {label}." for pattern, label in _PUBLISH_PATTERNS if pattern.search(text)]
    prose = _CODE_SPANS.sub("", text)
    problems += [f"The text contains {label}." for pattern, label in _RENDERED_PATTERNS if pattern.search(prose)]
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
    added_total = 0
    for tag, _, _, new_start, new_end in difflib.SequenceMatcher(
        None, old_lines, new_lines, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            continue
        added = new_lines[new_start:new_end]
        added_total += sum(1 for line in added if line.strip())
        if tag != "insert" or any(line.strip() and not _is_status_line(line) for line in added):
            problems.append(
                f"Line {new_start + 1}: only Fix attempted, Not fixed, and Left lines may be added; existing lines stay."
            )
    if added_total > MAX_ADDED_STATUS_LINES:
        problems.append(f"More than {MAX_ADDED_STATUS_LINES} status lines were added in one round.")
    return problems
