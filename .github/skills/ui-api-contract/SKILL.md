---
name: ui-api-contract
description: Keep frontend, backend, request-schema, and response-shape contracts aligned across UI and API changes.
---

# UI API Contract

Use this skill when frontend and backend changes must agree on one contract.

## Workflow

1. Trace each affected route to its request and response shapes.
2. Check frontend assumptions against backend schema, nullability, and payload semantics.
3. Keep route handlers thin when the repo expects service boundaries.
4. Update docs when route behavior or payload shape changes.

## Constraints

- Do not patch around a contract mismatch only in the UI when the backend contract is wrong.
- Do not silently broaden types without checking backend behavior.
- Do not let route handlers absorb business logic if the repo expects service helpers.

## Repo references

- `paper_trading_ui/backend/routes/`
- `paper_trading_ui/backend/schemas.py`
- `paper_trading_ui/frontend/src/`
- Related backend service modules

## Expected output

1. Contract surface touched
2. Drift findings or fixes
3. Validation summary across both stacks
