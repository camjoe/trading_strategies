# Docs Map

Type: map
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-07-02
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
| `.ai/` | Agent definitions (`agents/`) and skill definitions (`skills/`) — the canonical agent-guidance surfaces |
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
| `docs/architecture/service-cookbook.md` | Which function to call for common tasks | Service API signatures or function names change |
| `docs/architecture/service-repository-boundary.md` | Contract rules between service and repository layers | Layer boundary rules or exceptions change |

---

## Reference Notes and ADRs

Deep-dive references and decision records. Notes go stale when the thing they describe changes; ADRs rarely change (they record past decisions) but should be marked superseded if a decision is reversed.

### Notes

| File | What it covers | Goes stale when |
|---|---|---|
| `docs/reference/backtesting.md` | Backtesting commands, safeguards, and layering overview | `src/trading/backtesting/` interface or safeguards change |
| `docs/reference/broker-integration.md` | Broker abstraction, IB connection setup, live-trading safety | `src/infrastructure/brokers/` adapters or connection config change |
| `docs/reference/db-migration-system.md` | Hand-rolled SQLite migration system | `src/infrastructure/database/migrations.py` or migration conventions change |
| `docs/reference/accounts-schema-usage.md` | Account schema field usage patterns | Account schema or model fields change |
| `docs/reference/sleeve-schema-contract.md` | Sleeve schema contract between DB and domain | Sleeve table schema or `src/trading/models/` sleeve shapes change |
| `docs/reference/strategies.md` | Strategy signal models and processing | `src/trading/domain/strategy_signals.py` or strategy config changes |
| `docs/reference/runtime-jobs.md` | Runtime job entrypoint catalog — how to run and schedule each job | Runtime job entrypoints, scheduler flags, or task names change |
| `docs/reference/runtime-jobs-inventory.md` | Operator-facing job inventory: names, schedules, install commands | A job is added/removed or its schedule/install flags change |
| `docs/reference/db-schema.md` | Schema quick-reference (all tables, purposes, FKs) + semantic notes | A table is added or removed (drift-checked by `db_schema_check`) |
| `docs/reference/broker-setup-ibkr.md` | IBKR Client Portal Gateway operator setup checklist | IBKR gateway setup steps or connection config change |
| `docs/reference/broker-setup-alpaca.md` | Alpaca setup guide (Draft — adapter not implemented) | Alpaca adapter work starts or is dropped |
| `docs/reference/screenshot-ui.md` | UI screenshot / visual testing notes | UI layout or screenshot test tooling changes |
| `docs/reference/sentiment-signals.md` | Sentiment signal sources and integration | `src/infrastructure/feature_providers/` sentiment providers change |
| `docs/overview.md` | Definitive app explainer + north-star direction (entry point) | Purpose, capabilities, or high-level direction change |
| `docs/plan.md` | Tasks/order/status/timelines tracker (priority board P1..N + commitment tags) | A task ships, priorities change, or estimates are set |
| `docs/decisions.md` | Consolidated open decisions ("what needs defining") | A decision is made, added, or its status changes |
| `docs/sleeves-accounts-convergence.md` | Design detail for converging account/sleeve trading paths | Convergence design, workstreams, or the A/B stance change |
| `docs/db-schema-rewrite-spec.md` | Rationale + target for a clean DB rewrite (option B, greenfield) | DB rewrite scope, data-loss picture, or open decisions change |
| `docs/db-schema-target.md` | Proposed final schema on its own (WIP) | Target tables/columns change |
| `docs/developer-notes.md` | Developer gotchas + pre-implementation checks | Recurring dev pitfalls or required checks change |

### ADRs

| File | Decision recorded | Would be superseded by |
|---|---|---|
| `docs/adr/001-cross-platform-paths.md` | Use `pathlib.Path` for all paths | Switching away from pathlib |
| `docs/adr/002-backtesting-layering.md` | Backtesting module layering approach | Restructuring `src/trading/backtesting/` out of its current bounded-context shape |
| `docs/adr/003-sleeve-virtualization-architecture.md` | Sleeve virtualization architecture design | Wholesale redesign of the sleeve system |
| `docs/adr/004-runtime-naming-and-operational-settings.md` | "runtime" naming disambiguation; `operational_settings` package | Renaming the scheduler layer or the settings package |
| `docs/adr/005-models-as-lowest-data-layer.md` | `models/` holds all passive data contracts as the lowest layer | Restructuring the models layer or layering direction |
| `docs/adr/006-cross-cutting-decorators.md` | Sanctioned decorator/context-manager pattern for cross-cutting concerns | Changing the cross-cutting pattern rules |
| `docs/adr/007-ui-error-mapping.md` | Centralized UI domain-exception → HTTP mapping | Changing the backend error-mapping approach |
| `docs/adr/008-production-runtime-hosting-and-deployment.md` | Dedicated Linux host runs jobs from a `main`-tracking checkout; blue/green deferred | Moving to live trading / VPS, or adopting a hot-standby environment |

### Templates and Standards

| File | What it covers |
|---|---|
| `docs/adr/TEMPLATE.adr.md` | Template for new ADR files |
| `docs/reference/TEMPLATE.notes.md` | Template for new reference notes |
| `docs/reference/skill-invocation-policy.md` | Who can invoke which skill; `invoker` frontmatter schema and enforcement preamble convention |
| `docs/reference/agent-skills.md` | Copy of external upstream skill-authoring documentation (exempt from the doc-header standard) |

---

## Runbooks

Operational procedures. Go stale when workflows, job names, scripts, or DB operations change.

| File | What it covers | Goes stale when |
|---|---|---|
| `docs/runbooks/production-runtime-host.md` | Linux production host setup + test-and-deploy workflow promoting code to it | Host setup steps, deploy workflow, or branch/promotion model change |
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
| `docs/conventions/reference-doc.md` | Standard structure for reference notes | Reference doc conventions change |
| `docs/conventions/doc-header.md` | Required metadata header format for all docs/ files | Header fields, type vocabulary, or status vocabulary change |
| `docs/conventions/branching.md` | Branch model, naming rules, and commit restrictions | Branching strategy or naming conventions change |

---

## Agent Guidance — `AGENTS.md`, `.ai/`, and Conventions

Canonical rules loaded by Claude and other agents (`AGENTS.md` is the source of truth; `CLAUDE.md` imports it and `.github/copilot-instructions.md` redirects to it). These are the most authoritative docs in the repo — architecture maps and READMEs should agree with them, not the other way around.

### Conventions

| File | What it covers | Goes stale when |
|---|---|---|
| `docs/architecture/architecture-conventions.md` | Layering rules, dependency direction, import boundaries, package ownership | Any architectural boundary decision changes |

### Agents

| File | Agent scope | Goes stale when |
|---|---|---|
| `.ai/agents/backtesting-analyst.agent.md` | Backtesting analysis and reporting tasks | Backtesting API or workflow changes |
| `.ai/agents/broker-live-safety.agent.md` | Live-trading safety guardrails | Broker integration or live-trading safeguards change |
| `.ai/agents/db-migration-steward.agent.md` | DB migration authoring and review | Migration system conventions change |
| `.ai/agents/trading-runtime.agent.md` | Daily runtime job monitoring and intervention | Runtime job structure or job names change |

### Skills

Skills live under `.ai/skills/`. Each skill has a `SKILL.md` entry point plus zero or more sub-documents. The sub-documents refine or extend the skill; they go stale when the workflow they describe changes.

| Skill folder | What it covers |
|---|---|
| `check-pr-readiness/` | Pre-merge readiness checklist |
| `code-review/` | Code review at multiple thoroughness levels; sub-docs cover architecture, quality, style, UI/API contract |
| `create-runtime-job/` | Scaffold a new runtime job against the shared runner |
| `create-skill/` | Skill authoring workflow |
| `db-migration/` | Schema migration lifecycle (create, validate, estimate risk, rollback); restricted to the DB Migration Steward agent |
| `expand-tests/` | Test expansion workflow |
| `finance-strategy/` | Finance and strategy domain knowledge |
| `help/` | Interactive skill/agent discovery |
| `reference-doc/` | Reference-doc creation workflow |
| `update-documentation/` | Documentation update workflow; sub-docs cover docs-check and docs-sync |
| `update-skill/` | Skill update workflow |
| `validate-code/` | Code validation (lint, type-check, tests, layer-check) |

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

