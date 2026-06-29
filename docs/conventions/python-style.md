# Python Style Guide

Type: convention
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-06-29
Purpose: Project-specific interpretation of PEP 8, covering indentation, imports, naming, type hints, and ruff enforcement.
Related: [Doc Header Standard](doc-header.md)

This guide is the project-specific interpretation of [PEP 8](https://peps.python.org/pep-0008/).
It applies to all Python under `src/trading/`, `apps/paper_trading_web/backend/`, `scripts/`, `src/common/`, and `tests/`.

When PEP 8 is ambiguous or offers options, this guide picks one. Project rules take precedence over vanilla PEP 8.
Automated enforcement uses `ruff` (see [Enforcement](#enforcement) below).

---

## Table of Contents

1. [Core principle](#core-principle)
2. [Indentation and line length](#indentation-and-line-length)
3. [Blank lines](#blank-lines)
4. [Imports](#imports)
5. [String quotes](#string-quotes)
6. [Whitespace in expressions](#whitespace-in-expressions)
7. [Trailing commas](#trailing-commas)
8. [Naming conventions](#naming-conventions)
9. [Comments](#comments)
10. [Docstrings](#docstrings)
11. [Type hints](#type-hints)
12. [Programming idioms](#programming-idioms)
13. [File and path portability](#file-and-path-portability)
14. [Enforcement](#enforcement)
15. [Current state assessment](#current-state-assessment)

---

## Core principle

Code is read far more often than it is written.
Consistency within a module matters more than strict PEP 8 compliance.
Don't rewrite working code purely for style — apply improvements when touching a file for another reason.

---

## Indentation and line length

**4 spaces per level. No tabs.**

```python
# correct
def calculate(value: float) -> float:
    if value > 0:
        return value * 2
    return 0.0

# wrong — tabs
def calculate(value):
⇥   return value
```

**Maximum line length: 119 characters** (GitHub's display width).
Docstrings and comments should stay under 88 characters for readability in narrow windows.

Use Python's implicit continuation inside parentheses, brackets, and braces to break long lines.
Prefer breaking *before* binary operators (Knuth style):

```python
# correct
result = (
    gross_wages
    + taxable_interest
    - ira_deduction
)

# avoid
result = (gross_wages +
          taxable_interest -
          ira_deduction)
```

Don't use backslash continuations except where parentheses aren't available.

---

## Blank lines

- **Two blank lines** before and after top-level function and class definitions.
- **One blank line** between method definitions inside a class.
- Blank lines inside functions sparingly — only to separate distinct logical phases.
- No trailing whitespace on blank lines (invisible but flagged by linters).

---

## Imports

Group imports in this order, with one blank line between groups:

1. Standard library (`os`, `sqlite3`, `pathlib`, …)
2. Third-party packages (`pytest`, `requests`, …)
3. Local application (`trading.*`, `common.*`, `tests.*`)

```python
# correct
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from trading.repositories.accounts import get_account
from tests.support.seed_db import ACCT_TREND
```

Rules:
- One import per line for `import X` style.
- Multiple names on one line are fine for `from X import a, b, c` — but split to multi-line if it would exceed 119 chars.
- Absolute imports always preferred. Use relative imports (`from . import sibling`) only when the package layout makes absolute paths unwieldy.
- Never use wildcard imports (`from module import *`).
- `from __future__ import annotations` goes first, before standard library imports.

---

## String quotes

**Use double quotes** for all strings.
Use single quotes only to avoid escaping a double quote inside the string.

```python
# correct
name = "trading"
message = 'He said "hello"'  # single to avoid escaping

# avoid
name = 'trading'
```

Triple-quoted strings (docstrings and multiline strings) always use double quotes:

```python
"""This is a docstring."""
```

---

## Whitespace in expressions

**No extra spaces inside brackets:**
```python
# correct
spam(ham[1], {eggs: 2})

# wrong
spam( ham[ 1 ], { eggs: 2 } )
```

**No space before a colon, comma, or semicolon:**
```python
# correct
if x == 4: print(x, y)

# wrong
if x == 4 : print(x , y)
```

**No space before the parenthesis of a function call:**
```python
# correct
result = func(x)

# wrong
result = func (x)
```

**One space around assignment and comparison operators:**
```python
# correct
x = 1
if x == y:

# wrong
x=1
if x==y:
```

**No space around `=` in keyword arguments or default values for unannotated parameters:**
```python
# correct
def connect(host, port=5432):
    ...
connect(host="localhost", port=5432)

# wrong
def connect(host, port = 5432):
    ...
```

**Space around `=` when combining annotation with default:**
```python
# correct
def connect(host: str, port: int = 5432) -> None:
    ...
```

---

## Trailing commas

Use trailing commas on multi-line collections and argument lists. This makes diffs cleaner and avoids
accidental tuple creation when single-element tuples are intended:

```python
# correct — one item per line, trailing comma, closing delimiter on its own line
VALID_KINDS = [
    "trend",
    "momentum",
    "value",
]

# also correct for single-element tuple
FILES = ("setup.cfg",)
```

---

## Naming conventions

| Context | Style | Example |
|---|---|---|
| Module / package | `snake_case` | `backend.py`, `src/trading/` |
| Function / method | `snake_case` | `get_account()`, `_apply_rotation()` |
| Variable | `snake_case` | `account_id`, `sleeve_row` |
| Constant (module-level) | `UPPER_SNAKE_CASE` | `MAX_RETRIES`, `ACCT_TREND` |
| Class | `CapWords` | `SQLiteBackend`, `SleeveTradeIntent` |
| Type variable | `CapWords`, short | `T`, `AnyStr`, `KT_contra` |
| Exception | `CapWords` + `Error` suffix | `AccountNotFoundError` |
| "Private" function/var | `_single_leading_underscore` | `_build_query()` |
| Name-mangled attribute | `__double_leading` | `__internal_cache` (use sparingly) |

**Avoid:**
- Single-character names `l`, `O`, `I` (look like 1 and 0 in many fonts).
- `mixedCase` in new code (legacy only, for backwards compatibility).
- Abbreviated names that save 3 characters but cost 10 seconds of comprehension.

**Acronyms in CapWords:** capitalize the entire acronym — `HTTPServer`, not `HttpServer`.

---

## Comments

- Comments should explain *why*, not *what* (the code already shows what).
- Keep comments up to date. A stale comment is worse than no comment.
- Write in complete sentences with a capital first letter.
- Inline comments: two spaces before `#`, one space after. Use sparingly.

```python
# correct — explains intent
# Fallback to the default backend if none has been set yet.
backend = get_backend() or SQLiteBackend()

# avoid — restates the code
# Get the backend
backend = get_backend()
```

---

## Docstrings

Follow [PEP 257](https://peps.python.org/pep-0257/).
Triple double-quoted strings (`"""..."""`) always.

**One-line docstrings** — on a single line, no blank line before closing `"""`:
```python
def get_account(conn, name: str) -> sqlite3.Row:
    """Return the account row for *name*, raising KeyError if not found."""
```

**Multi-line docstrings** — summary on first line, blank line, then detail:
```python
def seed_session_db(conn: sqlite3.Connection) -> None:
    """Populate *conn* with the canonical test dataset.

    Call this exactly once per session (the ``seeded_conn`` fixture does this
    automatically).  The connection must be writable.  After seeding, open a
    read-only connection via URI ``?mode=ro`` for shared test access.
    """
```

Rules:
- Public modules, classes, and functions must have docstrings.
- Private helpers (`_prefixed`) benefit from docstrings when their behavior is non-obvious.
- Don't document parameters with a separate "Args:" section unless the signature alone is insufficient.
  Prefer a well-named signature + one-line summary over verbose boilerplate.

---

## Type hints

**Required for all public functions** (functions without a leading `_`).

```python
# correct — public function, fully annotated
def get_account(conn: sqlite3.Connection, name: str) -> sqlite3.Row:
    ...

# acceptable — private helper, annotation optional but encouraged
def _build_where_clause(filters: list[str]) -> str:
    ...
```

Rules:
- Use `from __future__ import annotations` at the top of every file to enable forward references without quotes.
- Prefer `X | None` over `Optional[X]` (Python 3.10+ union syntax works with `from __future__ import annotations`).
- Prefer `list[X]`, `dict[K, V]`, `tuple[X, ...]` (lowercase builtins) over `List`, `Dict`, `Tuple` from `typing`.
- Use `Iterator[X]` for generator functions and fixture return types.
- Use `Never` / `NoReturn` for functions that always raise.
- Annotate `-> None` explicitly on functions with no return value — it documents intent.
- Prefer read-only collection protocols for function parameters when mutation is
  not required. Use `Mapping[K, V]` instead of `dict[K, V]` for parameters that
  are only read, and use `Sequence[T]` instead of `list[T]` when callers do not
  need list-specific behavior. Keep concrete types for return values and mutable
  storage, e.g. return `dict[K, V]` when constructing a plain dict and use
  `dict[K, V]` for dataclass/model fields that callers may mutate or serialize.
  Apply this rule to new or touched signatures; do not churn existing code only
  to change collection annotations.

---

## Programming idioms

**Comparisons:**
```python
# correct
if x is None:
if x is not None:
if items:           # truthiness check for empty container
if not items:

# avoid
if x == None:
if items != []:
if len(items) == 0:
```

**Exception handling:**
```python
# correct — specific exception types
try:
    conn.execute(sql)
except sqlite3.OperationalError as exc:
    raise RuntimeError("Query failed") from exc

# avoid — bare except or too broad
try:
    ...
except Exception:
    pass
```

**String formatting — prefer f-strings:**
```python
# correct
message = f"Account {name!r} not found (id={account_id})"

# avoid
message = "Account %s not found (id=%d)" % (name, account_id)
message = "Account {} not found (id={})".format(name, account_id)
```

**Return type — don't return `None` explicitly at the end:**
```python
# correct
def register(name: str) -> None:
    _registry[name] = True

# avoid — redundant
def register(name: str) -> None:
    _registry[name] = True
    return None
```

**Comprehensions over map/filter for simple transforms:**
```python
# correct
names = [row["name"] for row in rows]

# avoid
names = list(map(lambda r: r["name"], rows))
```

---

## File and path portability

Use `pathlib.Path` for filesystem paths and prefer the shared helpers in `src/common/`
when formatting paths, resolving the repo Python executable, or comparing file
modified times across platforms.

Reach for these helpers in new or touched code:

- `common.paths.relative_posix(path, root)` when a path is displayed, logged, or
  compared as a repository-relative string. This avoids repeated
  `str(path).replace("\\", "/")` snippets.
- `common.paths.resolve_repo_python_exe(repo_root)` when scripts need the
  repository virtualenv Python executable. This centralizes the Windows
  `.venv\Scripts\python.exe` vs POSIX `.venv/bin/python` distinction.
- `common.files.modified_at_utc(path)` when code needs a timezone-aware file
  modified timestamp.
- `common.files.modified_at_iso(path)` when code returns or displays a file
  modified timestamp.
- `common.files.sorted_by_mtime_desc(paths)` or
  `common.files.latest_by_mtime(paths)` when selecting the newest file by
  modified time.

Keep platform-specific string normalization only at boundaries where the string
is input data rather than a filesystem path object, such as validating a user
provided route parameter.

---

## Enforcement

`ruff` is the linter. It runs in the CI check profile:

```bash
# CI (includes ruff)
.venv/bin/python -m scripts.run_checks --profile ci

# Quick local (mypy + pytest, no ruff yet)
.venv/bin/python -m scripts.run_checks --profile quick
```

When ruff enforcement is added to the quick profile, the config will live in `ruff.toml` at the repo root
with `line-length = 119` and the rule selections agreed by the team.

To run a manual style check now (assessment mode, no enforcement):
```bash
.venv/bin/ruff check src/trading/ apps/paper_trading_web/backend/ tests/ --select E,W,N --line-length 119 --statistics
```

---

## Current state assessment

Ruff scan run against `src/trading/`, `apps/paper_trading_web/backend/`, `tests/` on 2026-05-10
with `--select E,W,N --line-length 119`:

| Code | Count | Issue | Auto-fixable |
|---|---|---|---|
| E501 | 112 | Line exceeds 119 chars | No |
| N815 | 97 | Mixed-case variable in class scope | No |
| W293 | 51 | Trailing whitespace on blank line | Yes |
| W191 | 16 | Tab indentation | No |
| N803 | 4 | Invalid argument name (not snake_case) | No |
| W292 | 3 | Missing newline at end of file | Yes |
| W291 | 1 | Trailing whitespace | Yes |
| **Total** | **284** | | 46 auto-fixable |

**Observations:**
- **W191 (tabs)** — 16 files use tab indentation. This is a hard violation; editors typically hide it.
- **W293/W291 (invisible whitespace)** — 52 combined. Auto-fixable with `ruff check --fix`.
- **N815 (mixed-case in class scope)** — 97 occurrences likely reflect domain naming patterns (e.g., `camelCase` variables from third-party API shapes). Should be reviewed per file before enforcing.
- **E501 (line length)** — 112 violations even at 119 chars. These are genuine long lines that need manual wrapping.

This snapshot is a starting point. When the team decides to add enforcement, the recommended first pass is:
1. Auto-fix W293/W291/W292 (no behavior risk).
2. Address W191 (tab indentation) file by file.
3. Decide on N815 exclusions before enabling.
4. Work down E501 incrementally.
