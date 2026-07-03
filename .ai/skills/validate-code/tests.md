---
name: tests
description: Runs branch-targeted pytest suites for Python changes and vitest for frontend changes.
---

# Tests

## Python — branch-targeted

Run only the suites covering files changed on the branch:

```
python -m scripts.checks.run_suite --base develop
python -m scripts.checks.run_suite --base main
python -m scripts.checks.run_suite --no-cov --base develop   # faster, skip coverage
```

To target a specific suite explicitly:

```
python -m scripts.checks.run_suite src/trading/services/accounting
python -m scripts.checks.run_suite all
```

`run_suite` maps changed source paths to their test directories. Suite-to-source mapping is in `AGENTS.md`.

## Frontend — vitest

Run when any file under `apps/paper_trading_web/frontend/src/` is in the diff:

```
cd apps/paper_trading_web/frontend && npm test
cd apps/paper_trading_web/frontend && npm run test:coverage   # with coverage report
```

Use `python -m scripts.run_checks quick --with-frontend` or `python -m scripts.run_checks ci` when frontend files are in the diff.

## On failure

Non-zero exit. Print the failing test name, file, and assertion error. Do not skip or suppress failures — hand off to the user to fix before any AI review steps run.

## Repo references

- `scripts/checks/run_suite.py`
- `AGENTS.md` (suite-to-source mapping table)
- `apps/paper_trading_web/frontend/package.json`
