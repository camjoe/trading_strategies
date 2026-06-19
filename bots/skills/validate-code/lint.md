---
name: lint
description: Runs ruff lint and format checks (Python) and eslint + tsc type checking (frontend, when changed).
---

# Lint

## Python — ruff

```
python -m scripts.checks.ruff_check
```

Runs ruff lint and ruff format check. Does not auto-fix. Reports each violation with file and line.

To auto-fix (only when explicitly asked):

```
.venv/Scripts/python.exe -m ruff check --fix trading/ paper_trading_ui/backend/
.venv/Scripts/python.exe -m ruff format trading/ paper_trading_ui/backend/
```

## Frontend — eslint + tsc

Run when any file under `paper_trading_ui/frontend/` is in the diff.

```
cd paper_trading_ui/frontend && npm run lint
cd paper_trading_ui/frontend && npm run typecheck
```

`npm run lint` runs `eslint src --ext .ts`.
`npm run typecheck` runs `tsc --noEmit`.

<!-- TODO: add frontend lint + typecheck to scripts/checks/pr_ready.py when frontend files are in the diff -->

## On failure

Non-zero exit. Report each violation exactly as printed — do not paraphrase. Do not auto-fix unless asked.

## Repo references

- `scripts/checks/ruff_check.py`
- `paper_trading_ui/frontend/package.json`
- `docs/conventions/bot-style.md`
