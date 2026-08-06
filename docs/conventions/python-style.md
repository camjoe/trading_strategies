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
- Docstrings follow [PEP 257](https://peps.python.org/pep-0257/): one-liners on a single line;
  multi-line = summary line, blank line, detail.
- Public modules, classes, and functions must have docstrings; `_private` helpers when non-obvious.
- **No "Args:" boilerplate** unless the signature alone is insufficient — prefer a well-named
  signature + one-line summary.

---

## Type hints

Public production/tooling functions must carry return annotations, and modules must use
`from __future__ import annotations`; `python_conventions_check` enforces both. Private
helpers should be annotated when it clarifies a non-obvious contract.

- Prefer `X | None` over `Optional[X]` and lowercase builtins (`list[X]`, `dict[K, V]`)
  over `typing.List` etc.
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
