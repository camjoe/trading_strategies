# Branching

Type: convention
Status: Active
Created: 2026-06-24
Last Reviewed: 2026-06-24
Purpose: Define the branch model, naming rules, and commit restrictions used in this repository.
Related: [General Style](general-style.md), [Docs Map](../maps/docs-map.md)

## Branch Model

This repository uses a **main / develop** two-branch model.

| Branch | Role |
|---|---|
| `main` | Stable, production-ready code. No direct commits — changes arrive only via pull request. |
| `develop` | Integration branch. No direct commits (enforcement may not be applied, but the rule stands). Changes arrive only via pull request. |

All work branches off `develop`. When a feature or refactor is ready, open a PR against `develop`.

## Branch Naming

| Prefix | Use for |
|---|---|
| `features/[task]` | New functionality |
| `refactor/[task]` | Code restructuring without behavior change |
| `fix/[task]` | Bug fixes |
| `hotfix/[task]` | Urgent fixes applied directly to `main` (see Hotfix Flow below) |

Use lowercase kebab-case for `[task]` — e.g., `features/sleeve-promotion-api`, `fix/order-fill-rounding`.

## Workflow Summary

1. Branch off `develop`.
2. Do your work.
3. Open a PR against `develop`.
4. Merges to `main` are handled separately (release / promotion step).

## Hotfix Flow

When a critical fix must ship before `develop` is release-ready:

1. Branch `hotfix/[task]` off `main`.
2. Open a PR against `main`.
3. After merging, back-merge `main` into `develop` to keep them in sync.

## Branch Cleanup

Delete branches after merge — **except `refactor/` branches**, which may be kept for reference.

GitHub's auto-delete setting covers this for most cases; manually delete any that slip through.

## PR Titles and Descriptions

_To be determined._
