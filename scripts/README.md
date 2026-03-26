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
