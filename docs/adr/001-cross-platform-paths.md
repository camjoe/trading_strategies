# ADR: Cross-Platform Path Handling

Type: adr
Status: Accepted
Created: 2026-03-01
Last Reviewed: 2026-06-16
Purpose: Record a CI failure caused by Windows/Linux path separator differences so the rule to always use pathlib is documented.
Related: [DB Migration System](../reference/db-migration-system.md)

## What Happened

Local CI passed on Windows but GitHub Actions failed after push due to path separator differences.

Root cause: Windows tolerates backslashes (`\`) in path strings that Python constructs or passes to `os.path` functions. Linux does not — it treats `\` as a literal character. The failure surfaced as a file-not-found or import error that did not reproduce locally.

## Rules to Follow

- Use `pathlib.Path` for path construction, and `.as_posix()` only when building stable display/comparison strings.
- In tests, compare `Path` values or `.as_posix()` strings instead of raw platform-specific strings.
- `python -m scripts.checks.repo.path_safety_check --enforce` catches the common hazards; run the CI profile before pushing when path-handling code changes.
