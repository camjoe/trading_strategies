# Consolidation & Pruning Report

Tracks duplication to merge, content to freshen, and skills/agents/docs that may be dropped. This is the "Consolidation Report" deliverable. Grows during triage; resolved items stay here with their outcome.

## Phased approach (D-7)

| Pass | What | Rule |
|---|---|---|
| **0 — Triage** (before move) | Keep/drop call on each skill/agent/doc. **Mark only** — nothing edited or deleted. | Cheap; avoids migrating dead weight |
| **1 — Move** | Pure relocation + rename + link-fix (D-OPEN-10). | **No content changes** — keep diffs reviewable |
| **2 — Consolidate** (after move) | Merge overlaps, freshen stale content, dedupe. | Easier once everything is unified and overlaps sit side by side |

Note on D-5 (never delete information): "dropping" is a deliberate, reviewed decision recorded here; git retains history. Not silent loss.

---

## A. Consolidation candidates (merge / dedupe — Pass 2)

| # | Items | Overlap | Proposed action | Status |
|---|---|---|---|---|
| C1 | `python-style.md` + `style-guide.md` (was BOT_STYLE_GUIDE.md) | Both are code-style guides | Review together; likely merge into one. | open (D-OPEN-9) |
| C2 | `CLAUDE.md` "Docs Folder Guide" ↔ `docs/README.md` folder guide | Same folder-guide table in two places | Drop from CLAUDE.md; link to `docs/README.md`. | ✅ resolved (D-OPEN-8) |
| C3 | `AGENTS.md` "Key Reference Points" / "Keeping Docs Fresh" ↔ `docs/README.md` + `docs-map.md` | Reference lists restated | After move, point AGENTS.md at the docs index instead of restating. | open |
| C4 | `AGENTS.md` skill/agent inventory + routing tables ↔ each `SKILL.md` / `.github/skills/README.md` | Skill purposes listed in 2+ places | Decide single source for skill descriptions; others link. | open |
| C5 | `docs/business-rules/` (authoritative) ↔ web-app JSON | Same rules, two forms | JSON becomes derived (generated from docs or render docs). | open (D-OPEN-5) |
| C6 | `skill-invocation-policy.md` placement | It's normative (a policy/rule), currently in `reference/` | Decide: keep in `reference/` or move to `conventions/`. | open |

---

## B. Prune candidates — keep/drop triage (Pass 0)

**Cameron decides** — usage is his knowledge, not the agent's. Fill the Decision column; criteria below. Default is **keep** until reviewed.

> **Pass 0 status: COMPLETE (2026-06-17)** — one drop (`python-stat-modeling`); `help/` keep+reframe; `update-documentation` keep+Pass-2 rework; all other skills (9) and agents (4) kept as-is.

### Skills (`.github/skills/` → `bots/skills/`)

| Skill | Purpose (from AGENTS.md) | Decision |
|---|---|---|
| `check-pr-readiness/` | Pre-PR workflow: gate + review + report | KEEP |
| `code-review/` | All review modes | KEEP |
| `create-skill/` | Authoring new skills | KEEP |
| `db-migration/` | Schema migration lifecycle | KEEP |
| `expand-tests/` | Coverage/regression growth | KEEP |
| `finance-strategy/` | Financial terminology/strategy | KEEP |
| `help/` | Catalog of available skills/agents/prompts + how to use them (discoverability aid for Cameron) | **KEEP**, reframe — see note D1 below |
| `python-stat-modeling/` | Time-series / stat modeling | **DROP** (confirmed 2026-06-17) — see note D2 |
| `reference-doc/` | Reference docs & ADRs | KEEP |
| `update-documentation/` | Docs drift sync + staleness | **KEEP + Pass-2 rework** — see note D3 |
| `update-skill/` | Improve/refactor skills | KEEP |
| `validate-code/` | Deterministic validation | KEEP |

### Agents (`.github/agents/` → `bots/agents/`)

| Agent | Why it exists (from AGENTS.md) | Decision |
|---|---|---|
| `backtesting-analyst.agent.md` | Repo-specific backtesting/walk-forward flows | KEEP |
| `broker-live-safety.agent.md` | Broker safety + live-trading guardrails | KEEP |
| `db-migration-steward.agent.md` | SQLite migration safety + backup hygiene | KEEP |
| `trading-runtime.agent.md` | Runtime jobs, scheduler, operator behavior | KEEP |

### Keep/drop criteria

**Keep** if it: is invoked in real workflows; encodes repo-specific paths/safety/domain rules; has no better replacement.
**Drop** (mark, don't delete) if it: hasn't been used and you don't expect to; is superseded (e.g. by a deterministic script or another skill); describes a workflow that no longer exists.
**Defer** if usage is unclear — keep for now, revisit in Pass 2.

---

### Discoverability notes

**D1 — `help/` is a pull tool for a push problem.** Cameron's pain is recall: he forgets to use prompts that aren't auto-handled. `help/` requires remembering to invoke it — same failure mode. Resolution:
- **Keep `help/`, but recast it as a *generated* catalog** built from skill/agent `when-to-use` frontmatter (addition C) — so it never drifts. Generation/validation belongs with the deferred bots drift-check (D-OPEN-11). One source (frontmatter) → three views: `help/` catalog (pull), AGENTS.md routing (push), agent auto-trigger.
- **The real fix for "I forget" is push, not pull:** (1) maximize auto-trigger via good `when-to-use` descriptions so the agent selects tools without being asked; (2) add an AGENTS.md rule to surface a matching skill before proceeding.
- **Pass-2 task:** audit the manual prompts Cameron keeps forgetting → promote each to an auto-triggering skill or add it to AGENTS.md routing.

**D2 — `python-stat-modeling`: drop (pending confirm).** Zero transcript hits (incl. archived) → effectively never invoked. Content is a generic methodology checklist, not encoded expertise — wouldn't make an agent genuinely better at complex math/stats even when it fired. A non-triggering, shallow skill is routing noise. Drop = mark don't-migrate; git retains it. **Future idea (not a commitment):** author a real stat-modeling skill once Cameron has a working approach for getting agents to handle complex math/stats/modeling — likely repo-specific, with concrete techniques and references to `trading/backtesting/` + `trading/services/analysis/`.

**D3 — `update-documentation`: keep + serious Pass-2 rework.** It's the real docs-update mechanism (wired to `readme_check`, keyed off `docs-map` "goes stale when") but has been flaky because the substrate gave it no reliable staleness signal. This migration fixes that foundation (doc headers, `maps_check`, structured docs). Rework plan: (1) push deterministic detection onto `readme_check` + `maps_check`; (2) narrow `docs-sync` to the semantic targeted-update role; (3) `docs-check` is already a thin `readme_check` wrapper → likely collapses into the check tooling.

## C. Reference notes worth a freshness check (Pass 2)

The `reference/notes-*` files describe subsystems that may have drifted. Review for accuracy when consolidating (not now). Candidates flagged during triage go here.

**Staleness introduced by the develop merge (0f6c52f, reviewed 2026-06-17):** a large `trading/` refactor renamed repository APIs (e.g. `fetch_account_by_name` → `AccountRepository(conn).fetch_by_name()`, `update_account_fields` → `update`) and added models/repos/services. `service-repository-boundary.md` was updated in the merge, but these likely went stale and need a Pass-2 freshen:
- `docs/maps/trading-package-map.md` — module list + responsibilities (new models/repos/services).
- `docs/architecture/service-cookbook.md` — references old function names.
- `docs/architecture/nav-guide.md` — task→file lookups may point at renamed APIs.
- `docs/reference/db-schema.md` — **already badly incomplete** (lists 8 tables; codebase has sleeve/rotation/daily_metrics/promotion/strategy_param_sets too). Pre-existing, not merge-caused — reinforces D-9 (generate it). `db_schema.py` itself was *not* changed by the merge.

**Note:** Pass 1 (the move) is unaffected by the merge — no docs/skills/agents/entrypoints were added, removed, or renamed; `file-mapping.md` destinations all remain valid.
