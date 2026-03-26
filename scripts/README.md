# Scripts

Automation helpers for repository operations and CI/local quality checks.

## Docs Freshness

- `check_docs_freshness.py`: checks changed areas for missing documentation updates.
- `ci_smoke.py`: runs docs freshness, Python quality checks, tests, and optional frontend checks.

### Usage

```powershell
python scripts/check_docs_freshness.py
python scripts/check_docs_freshness.py --base-ref origin/main --head-ref HEAD
python scripts/ci_smoke.py --skip-frontend
```

## Cleanup Bot Prompt Prep

- `prepare_cleanup_bot_run.py`: builds a copy/paste-ready prompt for cleanup agents.

### Usage

```powershell
# Python bot on uncommitted files
python scripts/prepare_cleanup_bot_run.py --bot python --scope uncommitted

# Frontend bot on files changed since origin/main
python scripts/prepare_cleanup_bot_run.py --bot frontend --scope recent --base-ref origin/main

# Cross-stack bot on all relevant files
python scripts/prepare_cleanup_bot_run.py --bot both --scope all

# Project structure bot on recent changes
python scripts/prepare_cleanup_bot_run.py --bot structure --scope recent --base-ref origin/main
```

Optional JSON output:

```powershell
python scripts/prepare_cleanup_bot_run.py --bot both --scope uncommitted --json
```
