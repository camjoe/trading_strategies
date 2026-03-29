# Bot Architecture Conventions

Purpose: preserve consistent dependency direction, module ownership, and naming conventions across bot edits.

Scope:

1. This file defines architecture and API contract rules.
2. Formatting/style choices are out of scope here and live in `.github/BOT_STYLE_GUIDE.md`.

## Canonical Layering

Primary flow:

1. interfaces -> services -> repositories/domain -> database

Do not invert this flow.

## Allowed and Disallowed Dependencies

Allowed:

1. `trading/interfaces/*` importing `trading/services/*`
2. `trading/services/*` importing `trading/repositories/*` and `trading/domain/*`
3. `trading/repositories/*` importing `trading/database/*` helpers

Disallowed:

1. `trading/domain/*` importing interfaces/repositories/database modules
2. `trading/repositories/*` importing CLI/runtime adapters
3. `trading/interfaces/*` embedding persistence SQL or domain policy math that belongs in lower layers

## Package Ownership Map

1. `trading/interfaces/cli/`: CLI adapters and command wiring
2. `trading/interfaces/runtime/jobs/`: scheduler/runtime entrypoints
3. `trading/interfaces/runtime/data_ops/`: operator-facing maintenance flows
4. `trading/services/`: application orchestration and composition
5. `trading/domain/`: pure policy/decision logic (side-effect free)
6. `trading/repositories/`: SQL persistence adapters
7. `trading/database/`: DB infrastructure/config/coercion only
8. `trading/backtesting/`: same layered model within backtesting package

## Naming Conventions

General Python:

1. files/functions/variables: `snake_case`
2. classes/dataclasses: `PascalCase`
3. constants: `UPPER_SNAKE_CASE`

Repository naming:

1. reads: `fetch_*`
2. writes: `insert_*`, `update_*`, `delete_*`

Service naming:

1. read orchestration: `fetch_*`
2. side-effect workflows: `run_*`, `execute_*`
3. input/config derivation: `resolve_*`

Domain naming:

1. prefer descriptive policy/math names
2. avoid transport or persistence verbs

## Import and Facade Rules

1. Prefer direct imports from concrete implementation modules.
2. Avoid adding import-only facades unless they are deliberate public entrypoints.
3. Keep compatibility shims temporary and explicit.

## Abstraction and API Consistency

1. Keep top-level public modules thin and delegate orchestration to services.
2. Keep side-effect-free decision logic in domain modules.
3. Prefer explicit typed interfaces (dataclasses, TypedDict, Protocol) over generic `object` contracts.
4. Keep persistence and transport details out of domain contracts.
5. Avoid API drift: update docs/tests whenever public command/API behavior changes.

## Cross-Platform Safety

1. Use `pathlib`/OS-agnostic joins in Python code.
2. Do not hardcode slash direction (`/` vs `\\`) in runtime logic.
3. Keep command examples runnable from repo root and prefer `python -m ...`.
4. Avoid reliance on case-insensitive path behavior.
5. Make type narrowing explicit where mypy/platform inference may differ.

## Bot Placement Checklist

Before creating or moving code in `trading/`:

1. Classify change target: interface/service/domain/repository/database.
2. Place scheduler operations in `trading/interfaces/runtime/jobs/`.
3. Place operator data ops in `trading/interfaces/runtime/data_ops/`.
4. Keep SQL in repositories, not in handlers/routes.
5. Update `docs/architecture/trading-module-boundaries.md` if ownership boundaries change.
