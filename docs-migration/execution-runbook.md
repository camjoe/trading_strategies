# Execution Runbook — Pass 1 (the Move)

Ordered, checkbox procedure for executing the migration. Pass 0 (triage) is complete; this is **Pass 1** (pure relocation + rename + link-fix, no content merges). Pass 2 (consolidate/freshen) comes after. See [decisions.md](decisions.md) for the *why* behind each choice and [file-mapping.md](file-mapping.md) for the authoritative per-file destinations.

---

## Execution progress (2026-06-17)

**Moves + link sweep DONE & verified clean** (final stale-pattern grep returns nothing outside `docs-migration/`):
- `c068cf8` 1.1 docs reorg · `81605f7` 1.2 bots · `9a848ea` 1.3 BOT_* → docs · `a435546` 1.4 drops
- `8fd06f4` link wave 1 (basenames) · `7b3c4de` wave 2 (skills/agents/BOT_/python-stat-modeling) · `e5c0f5c` wave 3 (ADRs)
- Layer check passes; `layer_check.py` ruff-clean.

**Findings parked for later (not blockers):**
- Header backfill now includes **`docs/architecture/architecture-conventions.md`** and **`docs/conventions/bot-style.md`** (moved from `.github/`, predate the doc-header standard) — plus `naming.md` (1b) and `db-schema.md` (D-9). `agent-skills.md` stays exempt.
- **Pre-existing CI issue (NOT migration-caused):** `ruff` F401 unused import in `tests/trading/interfaces/runtime/data_ops/test_admin.py:8` (introduced by the develop merge). Auto-fixable with `ruff --fix`; handle separately from migration commits.

**Pass 1b DONE:** `naming.md`, thin `CLAUDE.md` + `.github/copilot-instructions.md`, `bots/README.md`, `CONTRIBUTING.md`; advisory-vs-enforced folded into `validate-code`; doc-headers backfilled on `architecture-conventions.md` + `bot-style.md`; `agent-skills.md` refs fixed. **D-8 revised:** `quality-gates.md` + `bot-authoring.md` dropped as redundant. Ruff F401 fixed (`45f2827`).

**Pass 1 COMPLETE.** Remaining is all deferred/Pass-2: D-9 (db-schema generation — `db-schema.md` still needs its header via the generator), D-OPEN-6 (`maps_check`), plus the Pass-2 consolidations and the freshness fixes from the develop merge.

## Guiding approach (Strategy A)

- **In-place `git mv` at repo root.** Reorganize the live `docs/` and `.github/` directly into final positions. `git mv` preserves rename history → reviewable diffs. There is **no physical staging in `agentswip/`** — that folder was the design sketch and gets deleted (its files are empty placeholders / dropped examples).
- **Commit in labelled chunks** (one per step group below) so each is independently reviewable and revertable.
- **Pass-1 purity:** the only content edits allowed are **mechanical path/link rewrites**. No merging, no freshening, no responsibility rewrites — those are Pass 2.
- **Exception — net-new files** (CONTRIBUTING, thin entrypoints, the new convention docs, `bots/README`) are *authored*, not moved; isolated in step group 1b so move-commits stay pure.
- *(Fallback Strategy B — assemble in `agentswip/` then promote — is possible but loses git rename tracking; not used unless you change this decision.)*

---

## Pre-flight

- [ ] On a dedicated branch — currently `refactor/docs-reorganization` ✅.
- [ ] Re-read [file-mapping.md](file-mapping.md) — it is the source of truth for every destination path.

**Working-tree state (verified 2026-06-17, after tracking commits):**
- Working tree is **clean**; everything is now committed, including `agentswip/` (38 files), `docs-migration/` (9 files), and the formerly-untracked `CLAUDE.md`, `docs/conventions/naming.md`, `docs/notes-db-schema.md`.
- `.gitignore` "# temp" block was **removed** — `docs-migration/` and `agentswip/` are tracked (decision: track the plan for history). No ignored-but-tracked mess.
- Because all files are tracked, **`git mv` works everywhere** and `agentswip/` deletion uses `git rm`.

---

## Step group 1 — Moves & renames (the core of Pass 1)

> Each sub-step is its own commit. Links **will** be broken between here and step 2 — that's expected; the link sweep fixes them all at once.

### 1.1 — docs/ internal reorganization
- [ ] Create folders: `docs/adr/`, `docs/business-rules/` (keep a `.gitkeep` in business-rules until D-OPEN-5 content lands).
- [ ] **ADRs** → numbered by `Created` date, into `adr/`: `001-cross-platform-paths` (2026-03-01), `002-backtesting-layering` (2026-03-27), `003-sleeve-virtualization-architecture` (2026-05-03). *(Done — verified from headers.)*
- [ ] `git mv docs/reference/TEMPLATE.adr.md docs/adr/TEMPLATE.adr.md`.
- [ ] **Reference notes** — drop `notes-` prefix: `backtesting.md`, `broker-integration.md`, `db-migration-system.md`, `accounts-schema-usage.md`, `sleeve-schema-contract.md`, `strategies.md`, `screenshot-ui.md`, `sentiment-signals.md`, `agent-skills.md`.
- [ ] **DB schema** (D-9): `git mv docs/notes-db-schema.md docs/reference/db-schema.md`. (Generation wiring is step 5; hand-written body stays as a stopgap until then.)
- [ ] **Conventions** — drop `-standard`/`-guide` via `git mv`: `doc-header.md`, `readme-layout.md`, `reference-doc.md`, `python-style.md`. `naming.md` keeps its path but its stub body is overwritten with `staged/naming.md` content (Pass-1b/edit).
- [ ] **Runbooks** — snake→kebab: `daily-operations.md`, `burn-in-protocol.md`, `governance-review.md`.
- [ ] Commit: `migrate(docs): reorg reference/adr/conventions/runbooks + rename to convention`.

### 1.2 — Create bots/ and move skills/agents/workflows
- [ ] Create `bots/`, `bots/agents/`, `bots/skills/`, `bots/workflows/`.
- [ ] `git mv .github/agents/*.agent.md bots/agents/` (4 files).
- [ ] `git mv .github/skills/<each>/ bots/skills/<each>/` — **11 skills** (NOT `python-stat-modeling`; that's dropped in 1.4).
- [ ] Leave **thin redirect** stubs in `.github/skills/` pointing at `bots/skills/` (D-OPEN-2) — minimal pointer content.
- [ ] Commit: `migrate(bots): move skills + agents to bots/, leave .github redirects`.

### 1.3 — Move .github convention docs into docs/
- [ ] `git mv .github/BOT_ARCHITECTURE_CONVENTIONS.md docs/architecture/architecture-conventions.md` (name 🟡 — confirm).
- [ ] `git mv .github/BOT_STYLE_GUIDE.md docs/conventions/bot-style.md` (parked for D-OPEN-9 merge review; move only).
- [ ] Commit: `migrate(docs): relocate BOT_* convention docs into docs/`.

### 1.4 — Drops (mark via removal; git retains history)
- [ ] `git rm -r .github/skills/python-stat-modeling/` (Pass 0 — D2; rewrite later).
- [ ] `git rm -r agentswip/` — now tracked (38 files). Empty placeholders + court-records examples + `generate_maps.py` stub, all superseded/dropped.
- [ ] Commit: `migrate: drop python-stat-modeling skill and agentswip scaffold`.

---

## Step group 1b — Author net-new structural files

> Net-new content (not moves). Draft from [staged/](staged/) and the cited decisions.

- [ ] `CONTRIBUTING.md` (root) — human contributor workflow (D-OPEN-8).
- [ ] `CLAUDE.md` (root) — rewrite thin: `@AGENTS.md` import + link `docs/README.md`; remove the duplicated Docs-Folder-Guide (D-OPEN-8 / consolidation C2).
- [ ] `.github/copilot-instructions.md` — thin redirect → `AGENTS.md` (D-OPEN-8). **Note:** develop's AGENTS.md already *references* this file ("read after AGENTS.md") but it doesn't exist yet — creating it resolves that dangling reference; match develop's framing.
- [ ] `docs/conventions/quality-gates.md` — rule → enforcing-check / DoD table (D-8 A).
- [ ] `docs/conventions/bot-authoring.md` — skill/agent frontmatter schema (D-8 C).
- [ ] `bots/README.md` — skill vs workflow vs agent + when-to-use (D-8 B).
- [ ] Commit: `migrate: add CONTRIBUTING, thin entrypoints, quality/authoring conventions, bots README`.

---

## Step group 2 — Link & path rewrite sweep (D-OPEN-10)

> Now that everything is at its final path, fix every reference in one pass.

- [ ] **AGENTS.md — heaviest file.** Rewrite all `.github/skills/...` → `bots/skills/...`, `.github/agents/...` → `bots/agents/...`, `.github/BOT_ARCHITECTURE_CONVENTIONS.md` → `docs/architecture/architecture-conventions.md`, `.github/BOT_STYLE_GUIDE.md` → `docs/conventions/bot-style.md`. Update the skill inventory (remove `python-stat-modeling`). *Keep* develop's existing additions: the platform-aware `.venv` paths and the `.github/copilot-instructions.md` reference (now resolved by 1b).
- [ ] **docs/README.md** — update all links to renamed/moved files.
- [ ] **docs/maps/docs-map.md** — the big one: it lists nearly every doc with old paths/names; update the inventory (or regenerate later via maps_check).
- [ ] **Doc-header `Related:` lines** — sweep every `docs/**` file for stale relative links (e.g. `doc-header.md`'s Related pointed at `reference-doc-standard.md` → `reference-doc.md`).
- [ ] **`doc-header.md` exception reference** — it names the header-exempt file as `notes-agent-skills.md`; update to `agent-skills.md`.
- [ ] **Root README.md** — `docs/reference/notes-backtesting.md` link → `docs/reference/backtesting.md`, etc.
- [ ] **Cross-doc references** — grep the repo for old paths (see Verification) and fix.
- [ ] Update the AGENTS.md schema note to point at the (soon-to-be-generated) `docs/reference/db-schema.md` (D-9).
- [ ] Commit: `migrate: rewrite internal links/paths to final locations`.

---

## Step group 3 — Tooling (may defer)

> Build tasks; can land in a follow-up if you'd rather verify the move first.

- [ ] Extend `scripts/data_ops/describe_db_schema.py` with a markdown write-mode; generate the schema block of `docs/reference/db-schema.md` between managed markers; fix the `db.py` source-of-truth note (D-9).
- [ ] Build `scripts/checks/maps_check.py` (drift-check, read-only); wire into `run_checks` advisory (D-OPEN-6).
- [ ] Commit each separately.

---

## Verification (gate before merge)

- [ ] **No stale paths remain:** grep the repo for old references —
  - `notes-` reference paths, `adr-` filenames, `.github/skills/`, `.github/agents/`, `BOT_ARCHITECTURE_CONVENTIONS`, `BOT_STYLE_GUIDE`, `_guide`/`_standard`/snake_case runbook names, `agentswip/`, `trading/database/db.py`.
- [ ] `python -m scripts.checks.readme_check` — passes/advisory only.
- [ ] `python -m scripts.run_checks --profile ci` — green (the move shouldn't touch code, but confirm nothing imported a moved path).
- [ ] Skills/agents still resolve from `.github` redirects (and/or your tool config points at `bots/`).
- [ ] Spot-check 3–4 moved docs render and their `Related:` links resolve.
- [ ] **Header coverage:** every `docs/` file has a `Type:` header except the documented exception `agent-skills.md`. (`naming.md` gets one in 1b; `db-schema.md` via D-9 generation.) Quick check: `grep -rL "^Type:" docs --include="*.md"` should list only `agent-skills.md` (+ TEMPLATEs).
- [ ] `git log --oneline` shows clean, labelled, per-group commits; `git mv` rename detection intact.

---

## Rollback

Every step is a discrete commit on a dedicated branch. To undo: `git revert <commit>` (preserves history) or reset the branch. Nothing is deleted destructively — dropped files remain in git history. Do **not** merge to `main` until verification passes.

---

## Explicitly NOT in Pass 1 (→ Pass 2)

- Merging the two style guides (D-OPEN-9).
- Reworking `update-documentation` (consolidation D3).
- Reframing `help/` as a generated catalog (D1 / D-OPEN-11).
- Freshening reference notes for accuracy (consolidation C).
- Transferring business-rules JSON content (D-OPEN-5).
- Enriching/cross-linking `scripts/` for agents (D-OPEN-12).

---

## Resolved: `docs-migration/` is tracked

Decision made 2026-06-17 — `docs-migration/` (and `agentswip/` until deleted) are committed to the branch so the plan and updates are visible in history. The "# temp" ignore block was removed. The folder can be deleted post-migration if desired.
