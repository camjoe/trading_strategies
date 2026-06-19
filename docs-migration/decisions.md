# Decision Log

Numbered record of decisions for the docs consolidation. `D-#` = decided; `D-OPEN-#` = open question (resolved ones keep their outcome). For current status and remaining work see [`README.md`](README.md).

---

## Decided

### D-1 — One source of truth
Consolidate `docs/` and the doc/agent/skill content of `.github/` into a single coherent structure. *Why:* a maintainable, AI-friendly repo needs one place agents can navigate reliably.

### D-2 — CI config stays in `.github/`
`.github/workflows/*.yml` and `.github/dependabot.yml` are out of scope and remain where GitHub requires them.

### D-3 — `.github/app/` removed
Stray misplaced Python was removed by Cameron. No longer a concern.

### D-4 — Resolve structure before moving
Finalize the target structure first; do not move source files until destinations are decided. The original migration prompt was a starting point, not a spec to execute literally.

### D-5 — Move freely; git is the safety net
Renaming/moving tracked files is fine. Prefer the easiest path: moving > rewriting > deleting; never delete information ("dropping" is a reviewed decision, recorded here — git retains history).

### D-6 — Extra scaffold folders kept for now
Retained as possibly-useful, removable later. (`examples/` since dropped per D-OPEN-4; `bots/agents/` kept as the merged agents home per D-OPEN-3.)

### D-7 — Migration runs in three phases
1. **Pass 0 — Triage** (before move): keep/drop call on each skill/agent/doc; mark only, nothing edited/deleted.
2. **Pass 1 — Move**: pure relocation + rename + link-fix; no content changes (keeps diffs reviewable).
3. **Pass 2 — Consolidate** (after move): merge overlaps, freshen, dedupe.

*Why:* mixing moves with edits makes diffs unreviewable; consolidation is easier once everything is unified.

**Pass-0 outcome (2026-06-17):** one drop — `python-stat-modeling` (zero usage + shallow generic checklist; reauthor later if a real repo-specific approach emerges). All other 9 skills + 4 agents kept; `help/` kept (reframe → D-OPEN-11); `update-documentation` kept (rework → D-OPEN-6).

### D-8 — Agent-correctness & quality layer
Considered three additions; **only `bots/README.md` (skill vs workflow vs agent surfaces) was kept.** A quality-gates/DoD doc and a bot-authoring standard were dropped as redundant — `validate-code`, `check-pr-readiness`, the existing `quality-gates.yml` workflow, `agent-skills.md`, `bots/skills/README.md`, and `create-skill` already cover them. The one genuinely-new bit (advisory-vs-enforced list) was folded into `validate-code/SKILL.md`.

### D-9 — DB schema doc
`docs/reference/db-schema.md` (moved from a mis-filed `docs/` root file; `notes-` prefix dropped). **Implemented as a drift *check*, not DDL generation:** a 25-table Quick Reference (purpose + FK per table) + authored semantic notes + doc-header, with full DDL left to `db_schema.py` (read it directly). `scripts/checks/db_schema_check.py` verifies the Quick Reference covers every live table (the maps_check "check the mechanical, author the meaning" model); wired into CI (advisory), tested. Corrected the source-of-truth error (the real sources are `db_schema.py` + `db_migrations.py`, not the non-existent `db.py`).

### D-10 — Execution strategy: in-place `git mv` (Strategy A)
Reorganized the live `docs/` + `.github/` directly into final positions with `git mv` (preserves rename history → reviewable diffs), authored net-new files fresh, then deleted the `agentswip/` scaffold. No physical staging in `agentswip/`. (Fallback "assemble in `agentswip/` then promote" rejected — it loses rename tracking.)

---

## Open questions

### D-OPEN-1 — Final name for the `agentswip/` root — ✅ RESOLVED
No `agentswip/` folder in the final version — it was a staging sketch only. Its contents promote to repo root (`CLAUDE.md`, `AGENTS.md`, `docs/`, `bots/`, `scripts/`, …).

### D-OPEN-2 — Skills/agents move to `bots/` — ✅ RESOLVED
Move them; breaking default tool discovery is acceptable (easy to fix). Authoritative copies live in `bots/`; tool-default locations (`.github/...`) become thin redirects. Cost: a duplication-drift surface — keep redirects thin (see Principles).

### D-OPEN-3 — Merge `bots/agents/` and `bots/prompts/` — ✅ RESOLVED
Collapse into a single `bots/agents/`; the persona files (architect, reviewer, refactorer, test-writer) move in. `bots/prompts/` dropped.

### D-OPEN-4 — How examples are handled — ✅ RESOLVED
Worked examples embed in the governing doc; no separate example files or `examples/` folders. `TEMPLATE.*` blanks stay co-located with what they template.

### D-OPEN-5 — `business-rules/` source of truth — ✅ RESOLVED (transfer deferred)
`docs/business-rules/` becomes authoritative; the web-app JSON becomes derived/secondary. **Remaining work:** transfer the JSON content into `docs/business-rules/`, then wire the web app to consume the docs (render markdown, or generate the JSON from docs) — never hand-maintain both.

### D-OPEN-6 — Map freshness tooling — ✅ RESOLVED + BUILT
**Drift-check, not generation** — maps interleave mechanical file-lists with authored responsibilities, so the script *reports* drift (files on disk missing from the map; map entries with no file) and never writes. Built `scripts/checks/maps_check.py` (section-aware, table-row-only matching, skips dir-summarized subtrees), covering all 3 structural maps (`trading-package`/`scripts`/`ui`) via `MAP_SPECS`; wired into CI (advisory, `--skip-maps-check`), tested. Domain maps excluded (purely authored). **Remaining work — `update-documentation` rework:** the checker now owns deterministic "is the inventory current?"; narrow the AI skill to the semantic role (writing/refreshing responsibilities and prose), and collapse the thin `docs-check` into the check tooling.

### D-OPEN-7 — Unify file-naming convention — ✅ RESOLVED
Written into `docs/conventions/naming.md`: `kebab-case.md` everywhere; reserved UPPERCASE tool names stay (`README`, `AGENTS`, `CLAUDE`, `CONTRIBUTING`, `SKILL`, `TEMPLATE.*`); folder conveys type so redundant prefixes/suffixes drop (`notes-`, `-guide`, `-standard`); ADRs numbered `NNN-title.md` chronologically by `Created` date; meaningful tool-read suffixes kept (`*.agent.md`, `TEMPLATE.*`).

### D-OPEN-8 — Root AI entrypoints — ✅ RESOLVED
`AGENTS.md` is canonical. `CLAUDE.md` thin (imports `@AGENTS.md`); `.github/copilot-instructions.md` thin redirect → `AGENTS.md`; `README.md` stays the human front door; a real `CONTRIBUTING.md` authored for contributor workflow. Ongoing discipline: keep the redirects thin, don't re-bloat.

### D-OPEN-9 — Style-guide consolidation — ✅ RESOLVED + EXECUTED
Style docs split by surface: `general-style.md` (cross-cutting balanced approach + docs/markdown style + index of the per-language guides), `python-style.md` (deep reference, unchanged), new `frontend-style.md` (TypeScript/Vite, expandable). Agent output-behavior moved to `AGENTS.md` (## Output style) for authority; AGENTS lists all three. Markdown/docs style stayed in `general-style.md` (broader than ADRs/reference docs — not folded into `reference-doc.md`). All refs updated; `docs-map.md` Conventions table refreshed.

### D-OPEN-10 — Internal link rewriting on rename/move — ✅ RESOLVED + BUILT
Every rename breaks relative links and doc-header `Related:` lines. Done at execution as a link-rewrite sweep (AGENTS.md was the heaviest). Now backstopped by `link_check.py` (markdown links + repo-path refs; advisory, wired into CI, tested).

### D-OPEN-11 — Agent self-verification tooling (deferred, future)
Considered, not adopted yet:
- **Skills/agents drift-check + generated catalog** — a `maps_check` sibling validating AGENTS.md routing ↔ actual `bots/skills` + `bots/agents`, so routing can't silently lie. The same generator feeds the `help/` catalog from one source (`when-to-use` frontmatter → help catalog, AGENTS routing, auto-trigger). This is the fix for "I forget to invoke the right prompt": push (auto-trigger / routing) beats pull (remembering to run `help`). Strong future item; revisit now that `maps_check` proves the pattern.
- **Skill evals** — automated tests that a skill triggers/behaves correctly. Premature; note for later.

### D-OPEN-12 — Agent understanding/use of `scripts/` (deferred, post-move)
Structure already supports this (no new folders): `scripts-map.md` (catalog), `runbooks/` (operational how-to), `reference/screenshot-ui.md` (subsystem detail). **Remaining work:** enrich `scripts-map` on usage + safety; cross-link operational scripts to the skills/agents that drive them (e.g. `screenshot_ui` ↔ a UI-verify skill; auto-trading runners ↔ `trading-runtime` + runbooks).

---

## Principles that outlast this migration

The folder shuffle was the easy, low-value part. The durable value is in the habits that fight documentation rot — spend energy here:

1. **Keep entrypoints thin.** The pull toward dumping everything into `CLAUDE.md`/`AGENTS.md` is constant. Push content into `docs/`; keep the redirects and imports thin.
2. **Generate or check the mechanical.** If a human/agent must remember to update something, it rots. Maps, schema, and (eventually) business-rules should be drift-checked or generated, not hand-maintained — the `maps_check`/`link_check`/`db_schema_check` pattern.
3. **Own the duplication seams.** Two consciously created — `.github/` redirects → `bots/`, and `docs/business-rules/` (authoritative) vs the web-app JSON (derived) — are the most likely "the docs lied to me" sources. Make the *other* side genuinely derived (a generator or pointer), never a hand-maintained twin.
4. **Doc-header discipline at creation time.** `Type/Status/Last Reviewed` headers + "goes stale when" columns are cheap to add when writing a file, expensive to retrofit — and the staleness tooling is only as good as the headers feeding it.
