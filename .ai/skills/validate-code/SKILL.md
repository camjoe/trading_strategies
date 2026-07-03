---
name: validate-code
description: Runs the repository's deterministic validation suite: layer boundary checks, ruff linting, mypy type checking, and targeted or full pytest runs. Use when asked to validate, lint, run tests, check code quality, or run checks before committing.
invoker: any
---

# Validate Code

All checks are deterministic — no AI, no reasoning. Each check has its own reference file.

## Checks (run in this order)

| Step | What | Reference |
|---|---|---|
| 1 | Repository checks | [layer-check.md](layer-check.md) |
| 2 | Python conventions, lint, type check, and tests | [lint.md](lint.md), [type-check.md](type-check.md), [tests.md](tests.md) |

## Run all checks at once

```
python -m scripts.run_checks repo
python -m scripts.run_checks python --base develop
python -m scripts.run_checks python --base main --no-cov
```

Run `repo` first, then `python`. Stop at the first failure.

## Day-to-day profiles

```
python -m scripts.run_checks quick
python -m scripts.run_checks ci
```

## On failure

Stop. Report the exact failing command and output — do not paraphrase. Do not proceed to any AI review steps. Hand back to the user to fix.

## Constraints

- Always use `.venv/Scripts/python.exe` (Windows) or `.venv/bin/python` (POSIX) — never system Python.
- Do not auto-fix lint errors unless explicitly asked. Run and report first.

## Not covered here (verify manually)

This suite is deterministic and does not check everything. These are **advisory** — confirm them by review, not by this suite:

- Naming conventions beyond what ruff covers (`docs/conventions/naming.md`)
- Reference notes and maps reflect current behavior (content accuracy — the CI profile's drift
  checks cover the mechanical: headers, links, maps, skills, generated assets)
- An ADR exists for any architectural decision

## Repo references

- `scripts/run_checks.py`
- `scripts/checks/repo_check.py`
- `scripts/checks/python_check.py`
