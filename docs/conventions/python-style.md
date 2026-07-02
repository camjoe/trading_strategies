# Python Style Guide

Type: convention
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-07-02
Purpose: The repo-specific Python rules on top of PEP 8 and ruff — line length, quotes, naming, type hints, docstrings, and path portability. Anything ruff auto-enforces is not restated here.
Related: [Doc Header Standard](doc-header.md)

This guide records only the decisions that are **specific to this repo** — where PEP 8 offers
options, or where we go beyond it. Baseline PEP 8 (whitespace, blank lines, comparison idioms,
comprehensions, f-strings) is assumed and enforced by `ruff`; it is deliberately not restated.
It applies to all Python under `src/trading/`, `apps/paper_trading_web/backend/`, `scripts/`,
`src/common/`, and `tests/`.

---

## Core principle

Code is read far more often than it is written.
Consistency within a module matters more than strict PEP 8 compliance.
Don't rewrite working code purely for style — apply improvements when touching a file for another reason.

---

## Line length and strings

- **Maximum line length: 119 characters** (GitHub's display width). Docstrings and comments should
  stay under 88 for readability in narrow windows.
- Break long lines with implicit continuation inside parentheses/brackets, breaking *before* binary
  operators (Knuth style). No backslash continuations where parentheses work.
- **Double quotes** for all strings (single only to avoid escaping a double quote inside).
  Docstrings always `"""..."""`.
- Trailing commas on multi-line collections and argument lists (cleaner diffs; ruff format's magic
  trailing comma preserves the multi-line shape).

---

## Imports

Groups in order, one blank line between: standard library → third-party → local
(`trading.*`, `common.*`, `tests.*`). `from __future__ import annotations` goes first in every file.
Absolute imports always; never wildcard imports.

---

## Naming

| Context | Style | Example |
|---|---|---|
| Module / function / variable | `snake_case` | `get_account()`, `sleeve_row` |
| Constant (module-level) | `UPPER_SNAKE_CASE` | `MAX_RETRIES` |
| Class | `CapWords` (acronyms fully capitalized: `HTTPServer`) | `SleeveTradeIntent` |
| Exception | `CapWords` + `Error` suffix | `AccountNotFoundError` |
| "Private" helper | `_single_leading_underscore` | `_build_query()` |

Model suffixes reflect lifecycle role — `*Config` (caller-facing partial input), `*Insert`
(repository-ready create payload), `*Record` (persisted read model). Canonical definition and
constants-placement rules: `docs/architecture/architecture-conventions.md`.

Avoid `l`/`O`/`I` single-char names, `mixedCase` in new code, and abbreviations that save 3
characters but cost 10 seconds of comprehension.

---

## Comments and docstrings

- Comments explain *why*, not *what*; complete sentences; keep them current (a stale comment is
  worse than none).
- Docstrings follow [PEP 257](https://peps.python.org/pep-0257/): one-liners on a single line;
  multi-line = summary line, blank line, detail.
- Public modules, classes, and functions must have docstrings; `_private` helpers when non-obvious.
- **No "Args:" boilerplate** unless the signature alone is insufficient — prefer a well-named
  signature + one-line summary.

---

## Type hints

**Required for all public functions** (no leading `_`); encouraged on private helpers.

- `from __future__ import annotations` everywhere; prefer `X | None` over `Optional[X]` and
  lowercase builtins (`list[X]`, `dict[K, V]`) over `typing.List` etc.
- `Iterator[X]` for generators and fixture return types; `Never`/`NoReturn` for always-raising
  functions; annotate `-> None` explicitly.
- **Read-only collection protocols for parameters:** take `Mapping[K, V]` / `Sequence[T]` when the
  function only reads; keep concrete `dict`/`list` for return values, mutable storage, and
  dataclass/model fields callers may mutate or serialize. Apply to new or touched signatures only —
  no annotation-churn passes.

---

## File and path portability

Use `pathlib.Path` for filesystem paths and prefer the shared helpers in `src/common/`
in new or touched code:

- `common.paths.relative_posix(path, root)` when displaying/logging/comparing a repo-relative
  string (avoids `str(path).replace("\\", "/")` snippets).
- `common.paths.resolve_repo_python_exe(repo_root)` for the venv interpreter (centralizes
  `.venv\Scripts\python.exe` vs `.venv/bin/python`).
- `common.files.modified_at_utc(path)` / `modified_at_iso(path)` for timezone-aware file mtimes.
- `common.files.sorted_by_mtime_desc(paths)` / `latest_by_mtime(paths)` for newest-file selection.

Keep platform-specific string normalization only at boundaries where the string is input data
rather than a filesystem path (e.g. validating a user-provided route parameter).

---

## Enforcement

`ruff` is the linter, configured in `ruff.toml` at the repo root (`line-length = 119`). It runs in
**both** check profiles:

```bash
# Quick local (README, layer, ruff, mypy, pytest)
.venv/bin/python -m scripts.run_checks --profile quick

# CI (quick gates plus doc-drift checks, dependency install, frontend)
.venv/bin/python -m scripts.run_checks --profile ci
```

For deterministic, behavior-preserving auto-fixes (ruff safe fixes + formatting):

```bash
.venv/bin/python -m scripts.fix_checks
```
