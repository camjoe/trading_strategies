# README Layout Standard

Type: convention
Status: Active
Created: 2026-04-24
Last Reviewed: 2026-04-25
Purpose: Define consistent README section layouts so contributors can write new README files with a predictable structure.
Related: [Doc Header Standard](doc-header.md)

## Purpose

Define consistent README section layouts so contributors can navigate docs quickly and write new README files with a predictable structure.

## Core Rules

- Keep one clear `# H1` at the top.
- Prefer short opening context, then operational steps.
- Use command examples that run from repo root (`python -m ...`).
- Link to deeper docs instead of duplicating long explanations.

## Layout Profiles

Use the profile that best matches the README scope.

### 1. Repo Root README

Required sections:

1. `## Project Overview`
2. `## Directory Structure`
3. `## Quick Start`
4. `## Testing`
5. `## Documentation Index`

Optional sections:

- `## Python Setup`
- `## CI Smoke Check`

Notes:

- `scripts.checks.readme_check` already validates the required root sections.

### 2. Module or Package README

Recommended section order:

1. `## Purpose`
2. `## Scope` (optional when useful)
3. `## Quick Start`
4. `## Commands` and/or `## Workflows`
5. `## Boundaries` / `## Architecture` (if ownership matters)
6. `## Related Docs`

Examples in this repo:

- `src/trading/README.md`
- `apps/paper_trading_web/README.md`
- `apps/trends/README.md`

### 3. Utility or Support README

Recommended section order:

1. `## Purpose`
2. `## Usage` or `## Commands`
3. `## Notes`

Examples in this repo:

- `tests/support/README.md`
- `.ai/skills/README.md`

## Section Naming Conventions

- Prefer `Quick Start` for first runnable commands.
- Prefer `Commands` for a command catalog.
- Prefer `Workflows` for multi-step operational flows.
- Prefer `Related Docs` for links out to deeper references.

## Author Checklist

Before finalizing a README:

1. Confirm at least one context section (`Purpose` or `Overview`).
2. Confirm at least one operational section (`Quick Start`, `Commands`, `Usage`, or `Workflows`).
3. Run:
   - `python -m scripts.checks.readme_check --max-age-days 90`
4. If behavior changed, update linked docs in the same change set.

