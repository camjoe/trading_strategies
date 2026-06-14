---
name: validate-code
description: Runs the repository's deterministic validation suite: layer boundary checks, ruff linting, mypy type checking, and targeted or full pytest runs. Use when asked to validate, lint, run tests, check code quality, or run checks before committing.
---

# Validate Code

All checks are deterministic — no AI, no reasoning. Each check has its own reference file.

## Checks (run in this order)

| Step | What | Reference |
|---|---|---|
| 1 | Layer boundary check | [layer-check.md](layer-check.md) |
| 2 | Lint (ruff + eslint/tsc if frontend changed) | [lint.md](lint.md) |
| 3 | Type check (mypy) | [type-check.md](type-check.md) |
| 4 | Tests (branch-targeted pytest + vitest if frontend changed) | [tests.md](tests.md) |

## Run all checks at once

```
python -m scripts.checks.pr_ready --base develop
python -m scripts.checks.pr_ready --base main
python -m scripts.checks.pr_ready --no-cov        # skip coverage overhead
```

`pr_ready` runs all four steps in order and stops at the first failure.

## Day-to-day profiles

```
python -m scripts.run_checks --profile quick      # layer + lint + tests
python -m scripts.run_checks --profile ci         # full suite + frontend
```

## On failure

Stop. Report the exact failing command and output — do not paraphrase. Do not proceed to any AI review steps. Hand back to the user to fix.

## Constraints

- Always use `.venv/Scripts/python.exe` (Windows) or `.venv/bin/python` (POSIX) — never system Python.
- Do not auto-fix lint errors unless explicitly asked. Run and report first.

## Repo references

- `scripts/checks/pr_ready.py`
- `scripts/run_checks.py`
