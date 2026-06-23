---
name: layer-check
description: Checks layer boundary violations in the trading package using static import analysis.
---

# Layer Check

Verifies that imports respect the defined layer hierarchy: interfaces → services → repositories/domain → database. No skipping layers, no reverse dependencies.

## Command

```
python -m scripts.checks.layer_check
```

Or as part of the full gate:

```
python -m scripts.checks.pr_ready --base <ref>
```

Layer check always runs first in `pr_ready`.

## What it checks

- Imports in `src/trading/interfaces/` do not reach into `src/trading/repositories/` or `src/infrastructure/database/` directly.
- `src/trading/services/` does not import from `src/trading/interfaces/`.
- `src/trading/repositories/` does not import from `src/trading/services/` or `src/trading/interfaces/`.

Rules are defined in `docs/architecture/architecture-conventions.md`.

## On failure

Non-zero exit. Output names the violating file and the illegal import. Fix the import before proceeding — do not bypass with `# noqa` or type-ignore.

## Repo references

- `scripts/checks/layer_check.py`
- `docs/architecture/architecture-conventions.md`
