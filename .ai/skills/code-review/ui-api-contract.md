---
name: ui-api-contract
description: Keep frontend, backend, request-schema, and response-shape contracts aligned across UI and API changes without letting UI layers absorb business logic or data-access responsibilities.
---

# UI API Contract

Use this skill when frontend and backend changes must agree on one contract.

## Workflow

1. Run or inspect `python -m scripts.checks.review_scope_check` to identify contract-scope files.
2. Trace each affected route to its request and response shapes.
3. Check frontend assumptions against backend schema, nullability, and payload semantics.
4. Keep route handlers thin and move business logic into service or canonical trading modules.
5. Reuse existing runtime or service modules instead of duplicating operator workflows in UI-specific code.
6. Update docs when route behavior or payload shape changes.

## Constraints

- Do not patch around a contract mismatch only in the UI when the backend contract is wrong.
- Do not silently broaden types without checking backend behavior.
- Do not let route handlers absorb business logic if the repo expects service helpers.
- Do not add raw SQL to route handlers when service, repository, or trading-layer boundaries already exist.
- Do not duplicate runtime data-ops or account-operation workflows inside `paper_trading_web`.

## Repo references

- `docs/architecture/architecture-conventions.md`
- `apps/paper_trading_web/backend/routes/`
- `apps/paper_trading_web/backend/services/`
- `apps/paper_trading_web/backend/schemas/`
- `apps/paper_trading_web/frontend/src/`
- `src/trading/` modules that should own canonical business behavior
- `apps/paper_trading_web/README.md`

## Expected output

1. Contract surface touched
2. Boundary map across routes, services, and canonical trading modules
3. Drift findings or fixes
4. Validation summary across both stacks
