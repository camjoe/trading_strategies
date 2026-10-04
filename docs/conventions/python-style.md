# Python Style Guide

Type: convention
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-07-13
Purpose: Repo-specific Python guidance that ruff cannot enforce: type-hint best practices, docstring expectations, and filesystem path handling.
Related: [General Style](general-style.md), [Architecture Conventions](../architecture/architecture-conventions.md), [Documentation Authoring Standard](docs-authoring.md)

Baseline PEP 8 (whitespace, blank lines, comparison idioms, comprehensions, f-strings) is enforced by `ruff` and is deliberately not restated here. For the cross-cutting style approach, see [General Style](general-style.md). For naming conventions, constants, imports, and line-length rules, see [Naming Conventions](../architecture/architecture-conventions.md#naming-conventions) and `ruff.toml`.

---

## Comments and docstrings

- Comments explain *why*, not *what*; complete sentences; keep them current (a stale comment is
  worse than none).
- **"Why" means a fact about the system, not the author's reasoning.** A comment earns its place
  when a reader would otherwise get something wrong — "batch ALTER rebuilds by copy-drop-rename, so
  foreign keys must stay off". It does not earn its place by recording deliberation: what you
  considered, what this replaced, what bug it fixed, why the old approach was worse.
- **Rationale for a change goes in the commit message.** Source is the worst place for it: the code
  gets edited and the story rots into a lie, while `git log`/`git blame` keep it accurate forever.
  Never narrate history in a file — no "this used to…", "X was removed because…", "previously this
  froze…".
- **Budget check.** If a change adds more prose lines than code lines, cut it back. That ratio is
  almost always narration rather than explanation.
- Docstrings follow [PEP 257](https://peps.python.org/pep-0257/): one-liners on a single line;
  multi-line = summary line, blank line, detail.
- Public modules, classes, and functions must have docstrings; `_private` helpers when non-obvious.
- **No "Args:" boilerplate** unless the signature alone is insufficient — prefer a well-named
  signature + one-line summary.

---

## Type hints

Public production/tooling functions must carry return annotations;
`python_conventions_check` enforces this. Private helpers should be annotated when it
clarifies a non-obvious contract.

`from __future__ import annotations` is **no longer required**. The repo targets Python
3.14+ (`requires-python`), where PEP 649 makes annotation evaluation lazy by default —
that already gives forward references, `TYPE_CHECKING`-only imports for cycle-breaking,
and no import-time cost, while keeping annotations resolvable for runtime introspection.
The future import only opts back into the older stringized behavior, so it adds nothing.
Existing occurrences are harmless and may stay; new modules do not need it.

- Prefer `X | None` over `Optional[X]` and lowercase builtins (`list[X]`, `dict[K, V]`)
  over `typing.List` etc.
- Import the abstract collection types — `Mapping`, `Sequence`, `Iterable`, `Iterator`,
  `Callable` — from `collections.abc`, not `typing`. These have no builtin spelling, so the
  rule above does not reach them; ruff's `UP035` enforces it. `typing` still owns what has no
  `collections.abc` equivalent: `Protocol`, `Any`, `cast`, `TYPE_CHECKING`, `TypeVar`.
- `Iterator[X]` for generators and fixture return types; `Never`/`NoReturn` for always-raising
  functions; annotate `-> None` explicitly.
- **Read-only collection protocols for parameters:** take `Mapping[K, V]` / `Sequence[T]` when the
  function only reads; keep concrete `dict`/`list` for return values, mutable storage, and
  dataclass/model fields callers may mutate or serialize. Apply to new or touched signatures only —
  no annotation-churn passes.

---

## Filesystem paths

Use `pathlib.Path` for filesystem paths. For repo-relative paths, logging, and cross-platform operations, prefer the shared helpers in `src/common/`:

- `common.paths.relative_posix(path, root)` when displaying/logging/comparing repo-relative paths.
- `common.git.get_repo_root(start)` to resolve the repository root.
- `common.files.modified_at_utc(path)` / `modified_at_iso(path)` for timezone-aware file mtimes.
- `common.files.sorted_by_mtime_desc(paths)` / `latest_by_mtime(paths)` for newest-file selection.

Keep platform-specific string normalization only at input boundaries (e.g. user-provided route parameters), never for filesystem paths.

---

## Timestamps

Any timestamp written to a database column goes through `src/common/time.py`:

- `common.time.utc_now_iso()` for "now".
- `common.time.as_utc_iso(value)` to render a `datetime` already in hand.
- `common.time.normalize_utc_iso(text)` for a timestamp arriving as text from outside (broker
  execution reports, imports). Raises on input it cannot parse rather than storing it.
- `common.time.parse_utc_iso(text)` to read one back.
- `common.time.next_date_str(date_str)` for the exclusive upper bound of a calendar day.

Do not call `datetime.isoformat()` directly on a value headed for a column. Stored timestamps are
compared as **strings** in SQL, so a column holding a mix of `Z`, `+00:00`, and bare-naive spellings
of the same instant does not order or range-filter correctly — `"…Z" < "…+00:00"` is False, and a
range bounded by a bare timestamp excludes the `Z`-suffixed value at the same instant.

For the same reason, filter a calendar day with a half-open range (`>= date_str AND < next_date_str(date_str)`)
rather than `substr(column, 1, 10)`: the range form uses the timestamp indexes, and a bare
`YYYY-MM-DD` bound sorts below every stored timestamp on that day whatever suffix it carries.

This rule is about persistence. In-memory `datetime` comparison (market hours, cache TTLs) and
`date.isoformat()` for a `YYYY-MM-DD` date column are unaffected.

---

## Tooling

- With the repository virtual environment active, run the normal Python quality gate through the
  project runner: `python -m scripts.run_checks python`.
- Run mypy through the project runner:
  `python -m scripts.checks.python.mypy_check`. Ad-hoc `mypy <file>` commands do not resolve the
  `src/` layout reliably and can report false import errors.
- The gate follows imports, so cross-module annotations are checked, not just documentation.
  It keeps `--ignore-missing-imports`, so unstubbed third-party packages (pandas, yfinance,
  `ib_async`) still resolve to `Any` — a call into one of those, and anything whose type comes
  back out of it, is unchecked. Pass `--follow-imports-skip` for a faster local pass, but a run
  under that flag proves nothing about cross-module types.
