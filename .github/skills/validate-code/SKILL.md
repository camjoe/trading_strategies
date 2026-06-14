---
name: validate-code
description: Runs the repository's deterministic validation suite: layer boundary checks, ruff linting, mypy type checking, and targeted or full pytest runs. Use when asked to validate, lint, run tests, check code quality, or run checks before committing.
---

# Validate Code

## Commands

**Full PR gate** (layer + lint + branch-targeted tests, fail-fast):
```
python -m scripts.checks.pr_ready --base develop
python -m scripts.checks.pr_ready --base main
python -m scripts.checks.pr_ready --no-cov        # skip coverage overhead
```

**Individual checks:**
```
python -m scripts.checks.layer_check              # layer boundary violations only
python -m scripts.checks.ruff_check               # ruff lint + format
python -m scripts.checks.mypy_check               # mypy type check
python -m scripts.checks.run_suite --base develop # branch-targeted tests
python -m scripts.checks.run_suite all            # full test suite
python -m scripts.checks.run_suite --changed      # tests for uncommitted changes
```

**Unified profiles:**
```
python -m scripts.run_checks --profile quick      # day-to-day: layer + lint + tests
python -m scripts.run_checks --profile ci         # CI-shape: full suite + frontend
```

## When to use which command

| Goal | Command |
|---|---|
| Before a PR | `pr_ready --base develop` |
| After uncommitted changes | `run_suite --changed` |
| Lint only | `ruff_check` + `mypy_check` |
| Layer boundaries only | `layer_check` |
| Full test suite | `run_suite all` |
| Day-to-day quick check | `run_checks --profile quick` |

## Fail-fast behavior

`pr_ready` stops at the first failing step and reports which step failed. Fix it and re-run.

Steps in order:
1. Layer boundary check
2. Ruff lint + format
3. Mypy type check
4. Branch-targeted pytest

## Constraints

- Always use `.venv/Scripts/python.exe` (Windows) or `.venv/bin/python` (POSIX) — never system Python.
- Report the exact failing command and output. Do not paraphrase errors.
- Do not auto-fix lint errors unless the user asks. Run and report first.

## Repo references

- `scripts/checks/pr_ready.py`
- `scripts/checks/layer_check.py`
- `scripts/checks/ruff_check.py`
- `scripts/checks/mypy_check.py`
- `scripts/checks/run_suite.py`
- `scripts/run_checks.py`
