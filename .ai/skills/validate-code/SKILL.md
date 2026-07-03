---
name: validate-code
description: Runs the repository's deterministic validation suite: layer boundary checks, ruff linting, mypy type checking, and targeted or full pytest runs. Use when asked to validate, lint, run tests, check code quality, or run checks before committing.
invoker: any
---

# Validate Code

All checks are deterministic — no AI, no reasoning.

## Checks (run in this order)

| Step | Command | What it covers |
|---|---|---|
| 1 | `python -m scripts.run_checks repo` | Layer boundaries, skills drift, live-trading safety, path safety, secret hygiene |
| 2 | `python -m scripts.run_checks python --base <base_ref>` | Python conventions, ruff, mypy, branch-targeted pytest |

## Run all checks at once

```
.venv\Scripts\python.exe -m scripts.run_checks repo
.venv\Scripts\python.exe -m scripts.run_checks python --base develop
.venv\Scripts\python.exe -m scripts.run_checks python --base main --no-cov
```

Run `repo` first, then `python`. Stop at the first failure.

## Day-to-day profiles

```
.venv\Scripts\python.exe -m scripts.run_checks quick
.venv\Scripts\python.exe -m scripts.run_checks ci
```

Use `quick --with-frontend` or `ci` when frontend files are in the diff. Use `python --suite <suite> --no-cov` for focused iteration.

## Single checks

Use these only when isolating a failure:

```sh
.venv\Scripts\python.exe -m scripts.checks.layer_check
.venv\Scripts\python.exe -m scripts.checks.ruff_check
.venv\Scripts\python.exe -m scripts.checks.mypy_check
.venv\Scripts\python.exe -m scripts.checks.run_suite <suite> --no-cov
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
