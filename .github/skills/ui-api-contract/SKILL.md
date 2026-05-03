---
name: ui-api-contract
description: Keep frontend, backend, request-schema, and response-shape contracts aligned across UI and API changes without letting UI layers absorb business logic or data-access responsibilities.
---

# UI API Contract

Use this skill when frontend and backend changes must agree on one contract.

## Workflow

1. Trace each affected route to its request and response shapes.
2. Check frontend assumptions against backend schema, nullability, and payload semantics.
3. Keep route handlers thin and move business logic into service or canonical trading modules.
4. Reuse existing runtime or service modules instead of duplicating operator workflows in UI-specific code.
5. Update docs when route behavior or payload shape changes.

## Constraints

- Do not patch around a contract mismatch only in the UI when the backend contract is wrong.
- Do not silently broaden types without checking backend behavior.
- Do not let route handlers absorb business logic if the repo expects service helpers.
- Do not add raw SQL to route handlers when service, repository, or trading-layer boundaries already exist.
- Do not duplicate runtime data-ops or account-operation workflows inside `paper_trading_ui`.

## Repo references

- `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- `paper_trading_ui/backend/routes/`
- `paper_trading_ui/backend/services/`
- `paper_trading_ui/backend/schemas.py`
- `paper_trading_ui/frontend/src/`
- `trading/` modules that should own canonical business behavior
- `paper_trading_ui/README.md`

## Expected output

1. Contract surface touched
2. Boundary map across routes, services, and canonical trading modules
3. Drift findings or fixes
4. Validation summary across both stacks
