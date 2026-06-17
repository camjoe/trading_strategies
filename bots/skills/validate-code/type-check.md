---
name: type-check
description: Runs mypy static type checking across the Python codebase.
---

# Type Check

## Command

```
python -m scripts.checks.mypy_check
```

Or as part of the full gate:

```
python -m scripts.checks.pr_ready --base <ref>
```

## What it checks

Runs mypy over `trading/` and `paper_trading_ui/backend/`. Reports type errors with file, line, and error code.

## On failure

Non-zero exit. Report the full mypy output — file, line, and error message exactly as printed. Do not suppress errors with `# type: ignore` unless the type stubs are genuinely wrong or missing for a third-party library.

## Repo references

- `scripts/checks/mypy_check.py`
- `mypy.ini` or `pyproject.toml` (mypy config, if present)
