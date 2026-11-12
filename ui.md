# Web UI Plan

Type: plan
Status: Active
Created: 2026-11-11
Last Reviewed: 2026-11-11
Purpose: Record the state of the Trading Workbench UI work on the features/command-catalog branch and list the open items.
Related: [UI Map](../maps/ui-map.md), [Web App README](../../apps/paper_trading_web/README.md), [UI Screenshot Utility](../reference/screenshot-ui.md), [Plans Index](README.md)

## Purpose

The web app (`apps/paper_trading_web`) became the **Trading Workbench**. The goal is a UI that is
more pleasant and more interesting to use, and that also fits broker trading, not only paper
trading. This plan records what shipped and what is still open.

## Shipped

All items are on the `features/command-catalog` branch. Nothing is pushed.

| Area | What changed | Commit |
|---|---|---|
| Header | App renamed to Trading Workbench (header, browser tab, API title). Logo mark, icon theme toggle, animated active-tab underline, tinted sub-tab band, compact phone layout. A DEMO badge shows in demo mode only. | `3c6866f2` |
| Theme | Dark is the default. A theme chosen with the toggle is saved and wins on the next load. | `7c068895` |
| Catalog families | Related entries share one row that opens to its members. Tools: 61 → 18 rows. CLI: 40 → 22. Jobs: 14 → 8. CLI families are in `CLI_FAMILIES` (`scripts/documentation_ui/commands/registry.py`); tool and job families are in `ENTRYPOINT_FAMILIES` (`entrypoints.py`). | `0e53f1a9`, `a6ceccd0`, `fbdf930f`, `8246a70e` |
| Catalog text | A row shows only the first paragraph of a parser description. | `58a2c29d` |
| Catalog filters | Risk filter buttons removed. The risk pill stays on each row. | `44fc7ec2` |
| Navigation | Documentation and Catalog merged into a **Reference** group: Markets, Software, API, then CLI, Jobs, Tools. Each docs page has section links. Each catalog page has its own search. Tab ids changed from `docs`/`catalog` to `docs-*`/`catalog-*`. | `7a7beaba` |
| Tools page | The Data and Database group opens with an embedded, lazy-loaded database diagram viewer. | `ea5212f0` |
| Tools page | The Quality Checks group opens with a live check runner: it runs each runnable check through `/api/catalog/run` and marks it passed, warned, or failed. | `88d63417` |

## Open Items

### 1. Commit the CI pipeline diagram (built, not committed)

The Quality Checks group has a CI pipeline card under the check runner. `scripts/documentation_ui/ci/`
reads `.github/workflows/ci.yml` and writes `assets/ci.json`. The card draws the triggers and jobs
from that file. The reference-docs check fails when the asset drifts from the workflow.

- **Decision:** approve the new `pyyaml==6.0.3` line in `requirements-dev.txt`. CI needs it for
  the drift check. The local venv has it only through `jupyter-events`.
- **Then:** commit the uncommitted CI files (generator, asset, card, tests, maps, READMEs).

### 2. Decide the docs hover menu

The old Documentation hover menu (`features/docs/menu.ts` and the `.docs-nav-*` CSS) is kept but
not called. The docs pages use section links now. Keep the section links and delete the menu code,
or restore the menu. To restore it, add the `#docsNavItem` dropdown to `views/nav.html` and call
`initDocsMenu(openTab)` from `features/docs/index.ts`.

### 3. Tune the section links

On a short docs page, for example Markets with all sections closed, the links repeat the section
headings below them. Options:

- Show the links only on pages with many sections.
- Make the links sticky while the page scrolls.

### 4. Give the diagram viewer a dark theme

The embedded viewer keeps its own light colors in the dark theme. The fix is in its generator,
`scripts/database_diagrams/html_viewer.py`, not in the frontend.

### 5. Draw the security workflow

The CI card draws only `ci.yml`. To add `security-checks.yml`, change the generator to read a list
of workflow files and show one pipeline for each.

### 6. Fix the scripts map warning

`maps-check` (shown with `!` in the check runner) reports 8 modules under `scripts/` with no row in
`docs/maps/scripts-map.md`, for example `scripts/documentation_ui/commands/build_registry.py`. Add
the rows, or confirm that the folder rows are sufficient.

### 7. Make more pages interesting

The Tools page has three showcase cards (`features/catalog-showcases.ts`). Find similar visuals
for other pages. Prefer live data or generated assets to screenshots, because screenshots go stale.

- The untracked `scn/` folder at the repository root holds 6 screenshots, for example
  `pythonCI.png` and `DiagramViewer.png`. Decide whether to use them (for example on the About page)
  or delete them.
- The check runner shows no output without a backend. A saved sample output is an option.

### 8. Rename "paper" where the app now also trades through a broker

These names are correct while all accounts are paper accounts. Change them when broker accounts
arrive:

- CLI help texts in `src/trading/interfaces/cli/` (`init`, `list-accounts`, `create-account`,
  `compare-strategies`).
- Job help texts and the module name `trading.interfaces.runtime.jobs.daily.paper_trading`.
- The `screenshot-ui` docstring ("paper trading UI").
- The package and folder `apps/paper_trading_web`. This rename touches many paths and needs its own
  change.

A per-account paper or live marker in the account view is a better signal than one global mode
badge, because the mode is set for each account.

## Notes for the Next Session

- Start the backend for live checks with the local `backend` entry in `.claude/launch.json`
  (ignored by Git), or with `python -m scripts.launch_ui`.
- A Vite config change needs a dev-server restart.
- The working copy uses CRLF line ends (`core.autocrlf=true`). A script edit that writes LF files
  is normalized by Git.
