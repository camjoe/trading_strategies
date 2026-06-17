# File Mapping (Migration Log)

Per-file tracker: where each source document ends up. Destinations use the **staging** root `agentswip/`. **Final paths drop the `agentswip/` prefix** — contents are promoted to repo root and the staging folder is deleted (see [D-1 / D-OPEN-1](decisions.md)). Example: `agentswip/docs/architecture/nav-guide.md` → final `docs/architecture/nav-guide.md`.

**Status:** 🟡 Proposed · ✅ Decided · ⬜ Open (no destination yet) · ⏭️ Stays put (out of scope)

> Nothing has been moved. "Status" tracks how settled the *destination decision* is, not whether the move happened. A separate "Moved?" column flips to ✓ during execution.

---

## docs/architecture/

| Source | → Destination | Status | Moved? | Notes |
|---|---|---|---|---|
| `docs/architecture/nav-guide.md` | `agentswip/docs/architecture/nav-guide.md` | ✅ | | already kebab |
| `docs/architecture/service-cookbook.md` | `agentswip/docs/architecture/service-cookbook.md` | ✅ | | already kebab |
| `docs/architecture/service-repository-boundary.md` | `agentswip/docs/architecture/service-repository-boundary.md` | ✅ | | already kebab |

## docs/conventions/

Kebab already; `-standard`/`-guide` suffixes **dropped** (D-OPEN-7 — folder denotes "standard").

| Source | → Destination | Status | Moved? | Notes |
|---|---|---|---|---|
| `docs/conventions/doc-header-standard.md` | `agentswip/docs/conventions/doc-header.md` | ✅ | | drop `-standard` |
| `docs/conventions/readme-layout-standard.md` | `agentswip/docs/conventions/readme-layout.md` | ✅ | | drop `-standard` |
| `docs/conventions/reference-doc-standard.md` | `agentswip/docs/conventions/reference-doc.md` | ✅ | | drop `-standard` |
| `docs/conventions/python-style-guide.md` | `agentswip/docs/conventions/python-style.md` | ✅ | | drop `-guide`; content review pending (D-OPEN-9) |
| `docs/conventions/naming.md` | `agentswip/docs/conventions/naming.md` | ✅ | | real content drafted in `staged/naming.md` |

## docs/reference/ → split into reference/ and adr/

| Source | → Destination | Status | Moved? | Notes |
|---|---|---|---|---|
Notes: `notes-` prefix dropped (D-OPEN-7 rule 3). ADRs → numbered `NNNN-title.md` (rule 4); numbers provisional, reorder to match real acceptance dates.

| `docs/reference/notes-backtesting.md` | `agentswip/docs/reference/backtesting.md` | ✅ | | drop `notes-` |
| `docs/reference/notes-broker-integration.md` | `agentswip/docs/reference/broker-integration.md` | ✅ | | drop `notes-` |
| `docs/reference/notes-db-migration-system.md` | `agentswip/docs/reference/db-migration-system.md` | ✅ | | drop `notes-` |
| `docs/reference/notes-accounts-schema-usage.md` | `agentswip/docs/reference/accounts-schema-usage.md` | ✅ | | drop `notes-` |
| `docs/reference/notes-sleeve-schema-contract.md` | `agentswip/docs/reference/sleeve-schema-contract.md` | ✅ | | drop `notes-` |
| `docs/reference/notes-strategies.md` | `agentswip/docs/reference/strategies.md` | 🟡 | | drop `notes-`; candidate source for business-rules extraction (D-OPEN-5) |
| `docs/reference/notes-screenshot-ui.md` | `agentswip/docs/reference/screenshot-ui.md` | ✅ | | drop `notes-` |
| `docs/reference/notes-sentiment-signals.md` | `agentswip/docs/reference/sentiment-signals.md` | ✅ | | drop `notes-` |
| `docs/reference/notes-agent-skills.md` | `agentswip/docs/reference/agent-skills.md` | ✅ | | drop `notes-` |
| `docs/reference/skill-invocation-policy.md` | `agentswip/docs/reference/skill-invocation-policy.md` | ⬜ | | could be conventions/ instead — normative (placement open, not naming) |
| `docs/reference/adr-backtesting-layering.md` | `agentswip/docs/adr/001-backtesting-layering.md` | 🟡 | | numbered (3-digit); confirm order |
| `docs/reference/adr-cross-platform-paths.md` | `agentswip/docs/adr/002-cross-platform-paths.md` | 🟡 | | numbered (3-digit); confirm order |
| `docs/reference/adr-sleeve-virtualization-architecture.md` | `agentswip/docs/adr/003-sleeve-virtualization-architecture.md` | 🟡 | | numbered (3-digit); confirm order |
| `docs/reference/TEMPLATE.adr.md` | `agentswip/docs/adr/TEMPLATE.adr.md` | ✅ | | reserved name; co-locate with type |
| `docs/reference/TEMPLATE.notes.md` | `agentswip/docs/reference/TEMPLATE.notes.md` | ✅ | | reserved name |
| `docs/notes-db-schema.md` (mis-filed at docs/ root) | `agentswip/docs/reference/db-schema.md` | 🟡 | | drop `notes-`; becomes generated-block + authored-notes (D-9); fix `db.py`→`db_schema.py`/`db_migrations.py` |

## docs/maps/

| Source | → Destination | Status | Moved? | Notes |
|---|---|---|---|---|
| `docs/maps/docs-map.md` | `agentswip/docs/maps/docs-map.md` | ⬜ | | may become generated (D-OPEN-6) |
| `docs/maps/trading-package-map.md` | `agentswip/docs/maps/trading-package-map.md` | ⬜ | | structural → generation candidate |
| `docs/maps/ui-map.md` | `agentswip/docs/maps/ui-map.md` | ⬜ | | structural → generation candidate |
| `docs/maps/scripts-map.md` | `agentswip/docs/maps/scripts-map.md` | ⬜ | | structural → generation candidate |

## docs/runbooks/

| Source | → Destination | Status | Moved? | Notes |
|---|---|---|---|---|
`snake_case` → `kebab-case` (D-OPEN-7 rule 1).

| `docs/runbooks/README.md` | `agentswip/docs/runbooks/README.md` | ✅ | | reserved name |
| `docs/runbooks/daily_operations.md` | `agentswip/docs/runbooks/daily-operations.md` | ✅ | | snake→kebab |
| `docs/runbooks/burn_in_protocol.md` | `agentswip/docs/runbooks/burn-in-protocol.md` | ✅ | | snake→kebab |
| `docs/runbooks/governance_review_guide.md` | `agentswip/docs/runbooks/governance-review.md` | ✅ | | snake→kebab; drop `-guide` (consistency with other runbooks) |

## docs/ root

| Source | → Destination | Status | Moved? | Notes |
|---|---|---|---|---|
| `docs/README.md` | `agentswip/docs/README.md` | ⬜ | | merge with existing scaffold README? |

## Root entrypoints (D-OPEN-8)

Final location = repo root (no `agentswip/` prefix). Scaffold's empty copies are dropped.

| Source | → Destination | Status | Moved? | Notes |
|---|---|---|---|---|
| `README.md` (root) | `README.md` | ✅ | | human front door; stays as-is |
| `AGENTS.md` (root) | `AGENTS.md` | 🟡 | | CANONICAL; rewrite its `.github/...` paths at execution (D-OPEN-10) |
| `CLAUDE.md` (root) | `CLAUDE.md` | 🟡 | | rewrite thin: `@AGENTS.md` + link `docs/README.md` (drop duplicated docs-folder guide) |
| — (new) | `.github/copilot-instructions.md` | 🟡 | | NEW thin redirect → AGENTS.md (Copilot used); to draft. AGENTS.md (post-develop-merge) already references it — dangling until created |
| — (new) | `CONTRIBUTING.md` (root) | 🟡 | | NEW real contributor workflow; to draft (staged) |
| `agentswip/{README,CONTRIBUTING,AGENTS,CLAUDE,copilot-instructions}.md` | — | 🗑️ drop | | empty scaffold placeholders; superseded by root files |

## .github/ — doc content (conventions, agents, skills)

| Source | → Destination | Status | Moved? | Notes |
|---|---|---|---|---|
| `.github/BOT_ARCHITECTURE_CONVENTIONS.md` | `agentswip/docs/architecture/architecture-conventions.md` (name 🟡, placement ⬜) | ⬜ | | SCREAMING_SNAKE→kebab decided; placement/merge open |
| `.github/BOT_STYLE_GUIDE.md` | `agentswip/docs/conventions/bot-style-guide.md` (name 🟡, placement ⬜) | ⬜ | | SCREAMING_SNAKE→kebab; may merge with python-style-guide |
| `.github/agents/*.agent.md` (4 files) | `agentswip/bots/agents/` | 🟡 | | authoritative (D-OPEN-2); merged with prompts (D-OPEN-3) |
| `.github/skills/` (11 of 12 migrate) | `agentswip/bots/skills/` | 🟡 | | authoritative; thin redirect in `.github/skills/` (D-OPEN-2). Pass 0: `python-stat-modeling` dropped (below) |
| `.github/skills/python-stat-modeling/` | — | 🗑️ drop | | Pass 0 — never invoked + shallow; rewrite later (consolidation.md D2) |
| `.github/copilot-instructions.md` (if present) | thin redirect → `bots/` / `AGENTS.md` | 🟡 | | stays in `.github/` as a pointer (D-OPEN-2, D-OPEN-8) |

### Scaffold `bots/prompts/` → merged into `bots/agents/`

| Source | → Destination | Status | Moved? | Notes |
|---|---|---|---|---|
| `agentswip/bots/prompts/*` (architect, reviewer, refactorer, test-writer) | `agentswip/bots/agents/` | 🟡 | | prompts/ folder dropped (D-OPEN-3); these are empty placeholders today |

## Scaffold-only — dropped, do NOT migrate (D-OPEN-4)

Court-records illustrations of file *shape*; not real content. Examples now embed in their governing doc instead.

| Scaffold file / folder | Status | Notes |
|---|---|---|
| `agentswip/docs/examples/` (empty) | 🗑️ drop | dedicated examples folder removed |
| `agentswip/bots/skills/examples/` (empty) | 🗑️ drop | dedicated examples folder removed |
| `agentswip/docs/maps/user-domain-map-example.md` | 🗑️ drop | illustration only |
| `agentswip/docs/maps/domains/budget-request-domain-example.md` | 🗑️ drop | illustration only |
| `agentswip/docs/conventions/service-layer-example.md` | 🗑️ drop | illustration only |
| `agentswip/docs/adr/decisions-example.md` | 🗑️ drop | illustration only |
| `agentswip/bots/skills/add-endpoint-example.md` | 🗑️ drop | illustration only |
| `agentswip/bots/workflows/production-bug-example.md` | 🗑️ drop | illustration only |
| `agentswip/scripts/generate_maps.py` (empty) | 🗑️ drop | superseded by `scripts/checks/maps_check.py` (drift-check, D-OPEN-6) |

## Out of scope — stays in .github/

| Source | Status | Notes |
|---|---|---|
| `.github/workflows/*.yml` (5) | ⏭️ | CI; GitHub-mandated location |
| `.github/dependabot.yml` | ⏭️ | GitHub-mandated location |

---

## Summary counts

- docs/ files to place: ~31
- .github/ doc items to place: 2 convention docs + 4 agents + 14 skill folders
- Gated on D-OPEN-2 (tool discovery): all skills + agents
- Out of scope (stays): 6 CI files
