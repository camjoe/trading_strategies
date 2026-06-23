# Migration Runbook (src/ restructure)

Type: runbook
Status: Draft
Created: 2026-06-22
Last Reviewed: 2026-06-22
Purpose: The repeatable, step-by-step procedure for moving one package/slice at a time into the target structure, keeping CI green and history clean at every commit. Pairs with [target-structure.md](target-structure.md).
Related: [Target Structure](target-structure.md), [Architecture Conventions](../architecture-conventions.md)

## Golden rules

- **One slice (or one layer of a large slice) per commit.** Never batch slices.
- **Every commit ends green.** Run the quick checks; do not commit red.
- **Tooling and docs move *with* the code in the same commit** — not as a later cleanup pass. (We have already seen unscoped moves leave ~77 broken doc links behind.)
- **`git mv` to preserve history.** Rewrite imports with a codemod, not by hand.
- **Tests move in the same commit as their source.**

## Phase 0 — Pre-flight (once, before any moves)

Do these before generating `FILE_MOVES.csv` / `COMMIT_PLAN.md`:

1. **Close the open decisions** D1–D5 in [target-structure.md](target-structure.md) (unmapped slices, `runtime` shape, `interfaces/api`, `models/` convention, `config/`).
2. **Redesign the layer check** to be slice-aware: match a layer *segment* anywhere in the dotted path (e.g. "any `*/domain/**` must not import `*.repositories.*` or `*.database.*`"), instead of fixed prefixes. Add tests for the new matcher. This must land before the first layered slice moves.
3. **Rewrite the layering docs** for the slice model: [architecture-conventions.md](../architecture-conventions.md) (Allowed/Disallowed + Ownership Map), and regenerate the maps.
4. **Write the import codemod** — a script that takes the `old.module.path → new.module.path` map from `FILE_MOVES.csv` and rewrites imports across `src/`, `apps/`, `scripts/`, `tests/`, and doc code-fences. Dry-run mode required.
5. **Confirm a green baseline:** `python -m scripts.run_checks --profile quick`.

### Phase 0.5 — Reconcile the moves already done

The `database → src/infrastructure` and `backtesting → src/trading` moves landed
*before* this runbook existed and left tooling/docs pointing at old paths. Clear
these so the foundation is trustworthy before building on it:

| Item | Status |
|---|---|
| Layer check: `trading.database.` rules were dead (module is now `infrastructure.database`) → repointed; services→database boundary re-enforced | **done** |
| Layer check: backtesting glob `trading/backtesting/services/**` was dead → moved to `src/trading/...` | **done** |
| Layer check: dead `trading.features` rule → repointed to `infrastructure.feature_providers.` | **done** |
| `architecture-conventions.md`: Ownership Map entries #6 (`trading/database`) and #8 (`trading/backtesting`) + Allowed/Disallowed still describe old paths | todo (folds into Phase 0 step 3 rewrite) |
| ~77 broken doc links + maps drift from the two moves | todo (`python -m scripts.checks.link_check` + `maps_check`) |
| Stale docstring ref `trading.database.config` in `src/infrastructure/database/backend.py` | todo (minor) |

## Per-move checklist (repeat for each slice)

> Example slice: `accounts`. Substitute the slice name throughout.

### 1. Start clean
- Working tree clean (`git status`), on the migration branch.
- Baseline green: `python -m scripts.run_checks --profile quick`.

### 2. Create the target package
- Make `src/trading/<slice>/` and its layer dirs (`domain/ models/ repositories/ services/`), each with `__init__.py`.
- Mirror the test tree: `tests/src/trading/<slice>/...` with `__init__.py` **at every level** (the existing `tests/src` and `tests/src/trading` chain is missing some — add them while here).

### 3. Move files (history-preserving)
- `git mv` each source file to its target per `FILE_MOVES.csv`, applying the prefix-drop renames (`account_config.py` → `config.py`).
- `git mv` the matching test files in the same commit.

### 4. Rewrite imports (codemod)
- Run the codemod with this slice's path map across `src/`, `apps/`, `scripts/`, `tests/`, and docs.
- Spot-check the diff; the codemod should touch only import lines (and doc code-fences).

### 5. Update tooling — same commit
- **Layer check** ([scripts/checks/layer_check.py](../../../scripts/checks/layer_check.py)): ensure the slice-aware rules cover the new paths; remove any now-dead flat rules.
- **Coverage** ([pytest.ini](../../../pytest.ini)): `--cov=src/trading` already covers new subpackages under `src/trading`; only edit if a new top-level package appears.
- **ruff / mypy targets** ([ruff_check.py](../../../scripts/checks/ruff_check.py), [mypy_check.py](../../../scripts/checks/mypy_check.py)): `src` is already a target; verify no path-specific entry was orphaned.
- **Editable install:** re-run `pip install -e .` **only** when a *new top-level* importable package appears under `src/` or `apps/` (e.g. introducing `shared` as `src/shared`). Reorganizing *within* `src/trading/` needs no reinstall — the namespace finder resolves new subpackages at import time.

### 6. Update docs — same commit
- [trading-package-map.md](../../maps/trading-package-map.md) and [docs-map.md](../../maps/docs-map.md): update paths/responsibilities for the moved slice.
- [architecture-conventions.md](../architecture-conventions.md): update the Ownership Map entry if this slice's ownership/placement changed.
- Fix any README/reference links that pointed at the old paths.
- Update the slice's row in [target-structure.md](target-structure.md) (`Status` → `done`).

### 7. Verify green
- `python -m scripts.run_checks --profile quick` (layer + ruff + mypy + tests). Fix until clean.
- Advisory: `python -m scripts.checks.link_check` and `python -m scripts.checks.maps_check` — clear them or record any residual in the commit body.

### 8. Commit
- One slice. Use the message template below.

## Per-commit message template

```
refactor(<slice>): move <slice> to src/trading/<slice> vertical slice

- git mv <n> source files + <m> test files (history preserved)
- drop redundant prefixes: <old> -> <new> (see FILE_MOVES.csv)
- codemod: rewrite imports across src/apps/scripts/tests/docs
- update layer_check rules, trading-package-map, conventions ownership
- run_checks --profile quick: green

Refs: docs/architecture/restructure/target-structure.md
```

## Definition of done (per move)

- [ ] Source + tests moved with `git mv`; prefixes dropped.
- [ ] Imports rewritten everywhere (no stale `trading.<old>` references: `git grep` clean).
- [ ] Layer check updated and passing for the new paths.
- [ ] Coverage still reports the slice's source; `--cov-fail-under` gate holds.
- [ ] ruff + mypy green including the moved files.
- [ ] Maps + conventions + affected README/reference links updated.
- [ ] `run_checks --profile quick` green.
- [ ] Single, scoped commit using the template.

## What NOT to do

- Don't batch multiple slices into one commit (defeats bisect/rollback).
- Don't hand-edit imports across the repo — use the codemod.
- Don't defer doc/tooling updates to a "cleanup later" commit.
- Don't move `infrastructure/` under `trading/` (see Hard constraints in the target doc).
- Don't move source without its tests.

## If a move goes wrong

- Each move is one commit, so `git revert <sha>` (or `git reset --hard` pre-push) cleanly backs out a single slice.
- The green checkpoint per commit means `git bisect` pinpoints any break to one slice.

## Order of moves

**Foundation before features.** Move and validate the shared/infrastructure base
*first*, so every slice that later depends on it is building on a proven, correct
foundation. Only then touch `src/trading/` business slices.

1. **Phase 0 + 0.5** — close decisions, redesign the layer check (the gate),
   write the codemod, reconcile the already-done moves, confirm green baseline.
2. **Foundation (do first, validate before proceeding) — see [foundation-commit-plan.md](foundation-commit-plan.md):**
   - **Relocate `trading/` → `src/trading/`** (+ tests) first — a pure `git mv`
     (imports unchanged) that collapses the split-namespace dual-path tooling and
     gives a single `src/` base. (Group 0.)
   - Extract the `yfinance` market-data adapter to `src/infrastructure/market_data/`
     (ports stay in domain) — the one remaining infra leak. (Group B.)
   - Seed `src/trading/shared/` from the cross-slice contracts in
     `src/trading/domain/`: `feature_provider` (11 importers), `broker_connection`
     (7), `exceptions` (5), `returns` (5). Optionally `common/` → `src/common/`.
   - **Checkpoint:** full `run_checks` green, and the shared/common import graph
     reviewed before any business slice moves.
3. **Leaf slices** with few cross-slice imports (`reporting`, `market_data`,
   `universe`) — exercise the codemod + checklist on low-risk packages.
4. **Layered business slices** (`accounts`, `promotion`, `evaluation`, `sleeves`).
5. **Cross-cutting last** (`runtime`, `interfaces`) — they touch the most call sites.
