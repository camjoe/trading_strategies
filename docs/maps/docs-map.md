# Docs Map

Type: map
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-07-22
Purpose: Full inventory of documentation files — use to audit staleness, find coverage gaps, and check for redundancy.
Related: [Docs README](../README.md), [Navigation Guide](../architecture/nav-guide.md)

Directory of all documentation files across the repository. Use this to audit for staleness, find coverage gaps, and check for redundancy between files.

---

## Top-Level Repository Directories

| Directory | Description |
|---|---|
| `src/trading/` | Core trading engine — layered Python package (interfaces → services → repositories → domain → database → models) |
| `apps/paper_trading_web/` | Operator UI — FastAPI backend + TypeScript/Vite frontend |
| `src/infrastructure/brokers/` | Broker adapters (paper + live); injected at the interface layer |
| `src/infrastructure/feature_providers/` | External-data feature providers for alternative strategies |
| `tests/` | Test suite; mirrors the source tree path-for-path |
| `scripts/` | Dev and ops tooling — checks, data ops, documentation sync, UI launcher |
| `docs/` | Architecture docs, runbooks, reference notes, ADRs, conventions |
| `src/common/` | Shared utilities available to all packages (used sparingly) |
| `apps/trends/` | Trend/signal data assets |
| `.ai/` | Skill definitions (`skills/`) — the repo's reusable task surface |
| `.github/` | Copilot-specific supplemental instructions (redirects to `AGENTS.md`) and CI workflows |

---

## How to Use This Map

- **Staleness check** — when code changes, use the "Goes stale when" column to identify which docs to review.
- **Coverage check** — scan "What it covers" to spot missing documentation for a new subsystem or workflow.
- **Redundancy check** — compare entries in the same section; overlapping "What it covers" fields signal duplication risk.

---

## READMEs

Orientation docs — typically the first thing read when entering a package. Go stale when package structure, entry points, or primary responsibilities change.

| File | What it covers | Goes stale when |
|---|---|---|
| `README.md` | Repo overview, setup, how to run | Project setup, major new packages added |
| `docs/README.md` | Docs folder navigation index; links to all maps and conventions | A doc file is added, moved, or removed |
| `src/trading/README.md` | `src/trading/` package overview and layering summary | Top-level `src/trading/` structure changes |
| `src/trading/backtesting/README.md` | Backtesting subsystem orientation | `src/trading/backtesting/` entry points change |
| `src/trading/interfaces/runtime/README.md` | Runtime surface index: which modules are runnable (scheduled/operator/worker) vs library | A runtime job, scheduling, or data-ops module is added/moved |
| `tests/README.md` | Test suite layout and how to run tests | Test runner, directory structure, or CI config changes |
| `tests/support/README.md` | Test support utilities and shared fixtures | `tests/support/` contents change |
| `apps/trends/README.md` | Trend/signal data assets | `apps/trends/` layout or data sources change |
| `scripts/README.md` | Dev and ops tooling orientation | Scripts added, removed, or renamed |
| `apps/paper_trading_web/README.md` | UI app orientation, how to run backend and frontend | UI entry points, ports, or dev workflow change |
| `docs/runbooks/README.md` | Runbook index | A runbook is added or removed |

---

## Architecture Maps

Structural reference — one file per major package. Go stale when module files are added, removed, renamed, or their responsibilities shift.

| File | What it covers | Goes stale when |
|---|---|---|
| `docs/maps/docs-map.md` (this file, top section) | Top-level directory overview | A new top-level directory is added or renamed |
| `docs/maps/trading-package-map.md` | Full `src/trading/` module directory; layering rules and placement decisions | Any `src/trading/` module added, removed, or its layer boundary changes |
| `docs/maps/ui-map.md` | `apps/paper_trading_web/` backend (routes, schemas, services) and frontend (features, components, lib, types, views, styles) | Any UI file added, removed, or restructured |
| `docs/maps/scripts-map.md` | All `scripts/` modules and their responsibilities | Scripts added, removed, or renamed |
| `docs/maps/infrastructure-map.md` | `src/infrastructure/` adapters, boundary rules, and config assets | Any `src/infrastructure/` module added, removed, or its boundary changes |
| `docs/maps/common-map.md` | `src/common/` shared-kernel utilities | Any `src/common/` module added, removed, or renamed |
| `docs/architecture/nav-guide.md` | Task → file lookup ("I want to X → edit Y") | A new task type emerges or a mapped file changes |
| `docs/architecture/service-cookbook.md` | Capability → service-package pointers + the stable import pattern | A service package is added/removed or a capability moves packages |
| `docs/architecture/service-repository-boundary.md` | Contract rules between service and repository layers | Layer boundary rules or exceptions change |

---

## Reference Notes and ADRs

Deep-dive references and decision records. Notes go stale when the thing they describe changes; ADRs rarely change (they record past decisions) but should be marked superseded if a decision is reversed.

### Notes

| File | What it covers | Goes stale when |
|---|---|---|
| `docs/reference/backtesting.md` | Backtesting commands, walk-forward terminology and evaluation standards, safeguards, and layering overview | `src/trading/backtesting/` interface, safeguards, or evaluation methodology changes |
| `docs/reference/broker-integration.md` | Broker abstraction, IB connection setup, live-trading safety | `src/infrastructure/brokers/` adapters or connection config change |
| `docs/reference/db-migration-system.md` | Numbered Alembic migration system: revisions, operator commands, runtime verification | `src/infrastructure/database/alembic/`, `migration_runner.py`, or migration conventions change |
| `docs/reference/database-transactions.md` | The `unit_of_work` / `commit_unit_of_work` pattern for grouping multiple DB writes into one atomic transaction | `src/trading/repositories/unit_of_work.py` or the repository-commit convention changes |
| `docs/reference/financial-market-knowledge.md` | Finance, market, and strategy glossary source for the documentation UI | Financial terminology or documentation UI glossary content changes |
| `docs/reference/strategies.md` | Strategy signal models and processing | `src/trading/domain/strategy_signals.py` or strategy config changes |
| `docs/reference/runtime-jobs.md` | Runtime job entrypoint catalog — how to run and schedule each job | Runtime job entrypoints, scheduler flags, or task names change |
| `docs/reference/db-schema.md` | Schema quick-reference (all tables, purposes, FKs) + semantic notes | A table is added or removed (drift-checked by `db_schema_check`) |
| `docs/reference/database-diagram-viewer.html` | Interactive generated database diagram viewer with full columns, grouped sections, relationship arrows, and toggleable FK metadata | Database schema, FK actions, or viewer generator changes |
| `docs/reference/broker-setup-ibkr.md` | IBKR Client Portal Gateway operator setup checklist | IBKR gateway setup steps or connection config change |
| `docs/reference/open-source-readiness.md` | Current public-source posture, continuous preparation rules, and final open-source licensing gate | Licensing posture, strategy-publication plans, security reporting, or release requirements change |
| `docs/reference/screenshot-ui.md` | UI screenshot / visual testing notes | UI layout or screenshot test tooling changes |
| `docs/reference/sentiment-signals.md` | Sentiment signal sources and integration | `src/infrastructure/feature_providers/` sentiment providers change |
| `docs/overview.md` | Current project capabilities, concepts, architecture, limitations, and scope (entry point) | Purpose, capabilities, architecture, limitations, or scope change |

### ADRs

| File | Decision recorded | Would be superseded by |
|---|---|---|
| `docs/adr/004-runtime-naming-and-operational-settings.md` | "runtime" naming disambiguation; `operational_settings` package | Renaming the scheduler layer or the settings package |
| `docs/adr/005-models-as-lowest-data-layer.md` | `models/` holds all passive data contracts as the lowest layer | Restructuring the models layer or layering direction |
| `docs/adr/006-cross-cutting-decorators.md` | Sanctioned decorator/context-manager pattern for cross-cutting concerns | Changing the cross-cutting pattern rules |
| `docs/adr/007-ui-error-mapping.md` | Centralized UI domain-exception → HTTP mapping | Changing the backend error-mapping approach |
| `docs/adr/008-production-runtime-hosting-and-deployment.md` | Dedicated Linux host runs jobs from a `main`-tracking checkout; blue/green deferred | Moving to live trading / VPS, or adopting a hot-standby environment |
| `docs/adr/010-book-keyed-execution-model.md` | Books are the execution primitive after sleeve retirement | Introducing another execution primitive or abandoning book-keyed flow |
| `docs/adr/012-runtime-alert-email-configuration.md` | Runtime SMTP alerts use environment variables | Moving SMTP settings into database or operator UI configuration |
| `docs/adr/014-execution-mode-collapse.md` | One book-keyed runtime path; rotation scheduling is book-owned, continuous eval under cooldown | Reintroducing an account-mode path or account-owned rotation config |
| `docs/adr/015-numbered-alembic-migrations.md` | Numbered Alembic revisions are the sole schema source; runtime verifies the head revision only, never migrates | Changing the migration approach, dependency scope, or runtime schema handling |

### Templates and Standards

| File | What it covers |
|---|---|
| `docs/adr/TEMPLATE.adr.md` | Template for new ADR files |

---

## Runbooks

Operational procedures. Go stale when workflows, job names, scripts, or DB operations change.

| File | What it covers | Goes stale when |
|---|---|---|
| `docs/runbooks/production-runtime-host.md` | Recommended dedicated Linux host setup + test-and-deploy workflow | Host setup steps, deploy workflow, or branch/promotion model change |
| `docs/runbooks/runtime-operations.md` | Daily + weekly-backup job monitoring, failure recovery, log inspection | Runtime job scripts or their schedule change |
| `docs/runbooks/burn-in-protocol.md` | Burn-in protocol steps for new strategies | Burn-in maintenance scripts or burn-in rules change |
| `docs/runbooks/governance-review.md` | Weekly/monthly governance review steps | Governance job scripts or review criteria change |

---

## Conventions

Rules and standards this project follows — coding style, doc structure, naming conventions.

| File | What it covers | Goes stale when |
|---|---|---|
| `docs/conventions/general-style.md` | Cross-cutting style approach + docs/markdown style; indexes the per-language guides | Style approach or doc-writing conventions change |
| `docs/conventions/python-style.md` | Python style conventions for this repo | Linting rules or project-wide conventions change |
| `docs/conventions/frontend-style.md` | TypeScript/Vite frontend style | Frontend conventions change |
| `docs/conventions/naming.md` | File/folder naming convention | Naming rules change |
| `docs/conventions/readme-layout.md` | Standard layout for README files | README section structure changes |
| `docs/conventions/docs-authoring.md` | Required metadata header, doc types, templates, and reference/ADR layouts for docs/ files | Header fields, type vocabulary, template, or section-layout rules change |
| `docs/conventions/branching.md` | Branch model, naming rules, and commit restrictions | Branching strategy or naming conventions change |

---

## Agent Guidance — `AGENTS.md`, `.ai/`, and Conventions

Canonical rules loaded by Claude and other agents (`AGENTS.md` is the source of truth; `CLAUDE.md` imports it and `.github/copilot-instructions.md` redirects to it). These are the most authoritative docs in the repo — architecture maps and READMEs should agree with them, not the other way around.

### Conventions

| File | What it covers | Goes stale when |
|---|---|---|
| `docs/architecture/architecture-conventions.md` | Layering rules, dependency direction, import boundaries, package ownership | Any architectural boundary decision changes |

### Skills

Skills live under `.ai/skills/`. Each skill has a `SKILL.md` entry point plus zero or more sub-documents. The sub-documents refine or extend the skill; they go stale when the workflow they describe changes.

| Skill folder | What it covers |
|---|---|
| `check-pr-readiness/` | Pre-merge readiness workflow (validation, AI review, docs advisory, report) |
| `code-review/` | Code review at multiple thoroughness levels, including architecture, quality, style, cleanup, and UI/API contract review |
| `create-runtime-job/` | Scaffold a new runtime job against the shared runner |
| `db-migration/` | Schema migration lifecycle (create, validate, estimate risk, rollback) |
| `expand-tests/` | Test expansion workflow |
| `finance-strategy/` | Finance and strategy domain knowledge |
| `help/` | Interactive skill discovery |
| `manage-skill/` | Skill authoring and update workflow |
| `reference-doc/` | Reference-doc creation workflow |
| `update-documentation/` | Documentation update workflow (staleness detection lives in CI) |
| `validate-code/` | Deterministic validation (repo checks + Python lint/type/test checks) |

---

## Consistency and Completeness Checklist

Use this when auditing documentation health:

- [ ] Every top-level directory in the "Top-Level Repository Directories" section above has a corresponding README.
- [ ] Every module listed in an architecture map file still exists on disk.
- [ ] ADRs whose decisions have been reversed are marked superseded.
- [ ] Reference notes describe current behavior (not past implementations).
- [ ] Runbooks reflect current job script names and paths.
- [ ] `docs/architecture/architecture-conventions.md` agrees with the architecture maps on import boundaries.
- [ ] `docs/README.md` links are not broken (no missing or renamed files).
- [ ] No two files in the same section cover the same scope without cross-referencing each other.
