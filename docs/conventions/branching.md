# Branching Workflow

Type: convention
Status: Active
Created: 2026-06-24
Last Reviewed: 2026-07-13
Purpose: Define the development, promotion, and hotfix branch workflow used in this repository.
Related: [Production Runtime Host Runbook](../runbooks/production-runtime-host.md), [Docs Map](../maps/docs-map.md)

## Branch Model

This repository uses a **main / develop** two-branch model.

| Branch | Role |
|---|---|
| `main` | Stable, production-ready code. No direct commits — changes arrive only via pull request. |
| `develop` | Integration branch. No direct commits (enforcement may not be applied, but the rule stands). Changes arrive only via pull request. |

Production runs from `main`. Development work starts from `develop` and merges back to `develop`.

## Branch Naming

| Prefix | Use for |
|---|---|
| `features/[task]` | New functionality |
| `refactor/[task]` | Code restructuring without behavior change |
| `fix/[task]` | Bug fixes |
| `hotfix/[task]` | Urgent fixes applied directly to `main` (see Hotfix Flow below) |

Use lowercase kebab-case for `[task]` — e.g., `features/book-rotation-api`, `fix/order-fill-rounding`.

## Daily Work

1. Update local `develop`.
2. Branch from `develop`.
3. Do the work on `features/...`, `fix/...`, or `refactor/...`.
4. Run the appropriate validation against `develop`.
5. Open a pull request into `develop`.

## Release / Promotion

1. When `develop` is ready to ship, open a pull request from `develop` into `main`.
2. Merge to `main`.
3. The production host pulls `main`; that merge is the deploy authorization point.

See [production-runtime-host.md](../runbooks/production-runtime-host.md) for the host-side pull and
restart workflow.

## Hotfix Flow

When a critical fix must ship before `develop` is release-ready:

1. Branch `hotfix/[task]` off `main`.
2. Open a PR against `main`.
3. After merging, back-merge `main` into `develop` to keep them in sync.

## Branch Cleanup

Delete branches after merge — **except `refactor/` branches**, which may be kept for reference.

GitHub's auto-delete setting covers this for most cases; manually delete any that slip through.
