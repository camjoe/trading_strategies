# Project-Agnostic Tooling Plan

Type: plan
Status: Draft
Created: 2026-07-13
Last Reviewed: 2026-10-11
Purpose: Define which developer scripts could become reusable tools with per-project config, what moves to config, and the trigger that makes the extraction worth doing.
Related: [UI Screenshot Utility](../reference/screenshot-ui.md), [Scripts Map](../maps/scripts-map.md), [Documentation Maintenance](../conventions/documentation-maintenance.md), [Plans Index](README.md)

## Purpose

Extract selected scripts into small tools that other projects can use. The repository keeps its
own policy in config and thin wrappers. This is not current work. The trigger below starts it.

## Principle

Extract reusable engines. Keep project policy in the project. Each tool is a small CLI with a
strict config file. Do not build one broad automation framework.

## Candidates

### 1. UI screenshot verifier (first candidate)

Source: `scripts/screenshot_ui.py` (about 250 lines). The Playwright flow is generic. These parts
are hardcoded in `capture()` and move to config:

| Hardcoded now | Config field |
|---|---|
| `.tab-nav` ready selector | page-ready selector |
| `[data-tab="…"]` and `[data-nav-group]` navigation | a list of navigation steps (click selector, optional group) |
| `[data-account="…"]` account card | an optional named action |
| `#analysisPanel` and the "Loading analysis" text | a named wait rule (selector, text-absent condition, timeout) |
| `TAB_SETTLE_MS`, `ANALYSIS_TIMEOUT_MS` | wait settings |
| `DEFAULT_URL` from `scripts/ui_config.py` | base URL |
| `SCREENSHOTS_DIR` from `common.paths` | output directory |
| tab names in the `--tab` help text | scenario names |

Keep `python -m scripts.screenshot_ui` as a thin wrapper with the same flags. Compare old and new
output for the existing tabs before you remove the old code.

### 2. Check runner

Source: `scripts/checks/_runner.py`. `CheckStep` and `run_check_steps` are already generic: ordered
steps, fail fast, skip flag. The profiles (`quick`, `ci`, `docs`, `repo`, `python`) are in code in
`scripts/run_checks.py` and `scripts/checks/`. The missing piece is a config file that lists the
steps of each profile. Extract this only after the screenshot config format has proved itself.

### 3. Documentation catalog generators

Source: `scripts/documentation_ui/` (commands, software, and CI generators that write the JSON
assets of the catalog). The generators scan the repository and write JSON that the frontend reads.
The scan logic is project-specific. Treat this as out of scope until a second project needs a
catalog. Record the decision here so nobody extracts it by accident.

### 4. Diagram and report helpers

`scripts/database_diagrams/` generates database diagrams. Extract nothing until there is a repeated
need in another project.

## Stays in this repository

Do not extract these:

- database schema checks and fixers
- broker integration and live-trading safety workflows
- runtime job inspection and scheduling policy
- documentation map semantics
- architecture rules for `src/trading/`

## Trigger

Start only when one of these holds:

- another project needs the screenshot or check-runner workflow
- the config in `scripts/` is harder to maintain than a package boundary would be
- CI or agent workflows need a stable tool interface across repositories

No second project exists today, so this plan stays a draft.

## Acceptance criteria for the first extraction

- The generic tool runs from a project config file.
- `python -m scripts.screenshot_ui` keeps its flags and output path rules.
- Output matches the current output for every existing tab.
- Selectors, routes, and labels stay outside the generic package.

## Related Docs

- [UI Screenshot Utility](../reference/screenshot-ui.md) — current usage of the script
- [Scripts Map](../maps/scripts-map.md) — inventory of `scripts/`
