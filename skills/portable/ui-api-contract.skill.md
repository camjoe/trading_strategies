---
name: UI API Contract Steward
layer: portable
description: Portable starter skill for keeping frontend, backend, and request-schema contracts aligned.
use_when:
  - frontend and backend both changed
  - API payloads or route schemas changed
  - UI data assumptions may have drifted from backend responses
localize_with:
  - frontend root path
  - backend route and schema locations
  - validation commands for both stacks
---

## Goal

Prevent frontend/backend drift by treating routes, schemas, and UI expectations as one contract.

## Responsibilities

1. Trace each affected route to its request and response shapes.
2. Check that frontend usage matches backend schema and nullability.
3. Keep route modules thin and move business logic into service helpers where the repo expects it.
4. Update docs when route behavior or payload shape changes.

## Constraints

1. Do not patch around schema mismatch only in the UI when the contract is wrong.
2. Do not silently broaden types without verifying backend behavior.
3. Do not let route handlers own database logic if the repo expects service boundaries.

## Localize for a project

Fill in:

- frontend and backend roots
- route modules and schema files
- API validation and frontend type-check commands

## Expected output

1. Contract surface touched
2. Drift findings or fixes
3. Validation summary across both stacks
