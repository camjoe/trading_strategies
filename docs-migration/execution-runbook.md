# Execution Runbook — Pass 1 (the Move)

Ordered, checkbox procedure for executing the migration. Pass 0 (triage) is complete; this is **Pass 1** (pure relocation + rename + link-fix, no content merges). Pass 2 (consolidate/freshen) comes after. See [decisions.md](decisions.md) for the *why* behind each choice and [file-mapping.md](file-mapping.md) for the authoritative per-file destinations.

---

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

**Working-tree specifics (verified 2026-06-17):**
- `.gitignore` "# temp" block ignores `app/`, `agentswip/`, `docs-migration/`. So `docs-migration/` (this plan) and `agentswip/` are **not tracked**.
- `agentswip/` has **0 tracked files** → Step 1.4 deletes it with a plain `rm -rf` / `Remove-Item -Recurse` (no `git rm`).
- These real files are **untracked** (never committed): `CLAUDE.md`, `docs/conventions/naming.md`, `docs/notes-db-schema.md`. `git mv` does **not** work on untracked files — use plain `mv` then `git add` at the destination (noted inline below).
- Uncommitted `.gitignore` (M) edit is unrelated to Pass 1; leave or commit separately.
- **Open question:** keep `docs-migration/` gitignored (local-only) or track it for history? See note at end.

---

## Step group 1 — Moves & renames (the core of Pass 1)

> Each sub-step is its own commit. Links **will** be broken between here and step 2 — that's expected; the link sweep fixes them all at once.

### 1.1 — docs/ internal reorganization
- [ ] Create folders: `docs/adr/`, `docs/business-rules/` (keep a `.gitkeep` in business-rules until D-OPEN-5 content lands).
- [ ] **ADRs** → numbered, into `adr/`: `git mv docs/reference/adr-backtesting-layering.md docs/adr/001-backtesting-layering.md` (then 002 cross-platform-paths, 003 sleeve-virtualization-architecture). Confirm numbering matches acceptance order.
- [ ] `git mv docs/reference/TEMPLATE.adr.md docs/adr/TEMPLATE.adr.md`.
- [ ] **Reference notes** — drop `notes-` prefix: `backtesting.md`, `broker-integration.md`, `db-migration-system.md`, `accounts-schema-usage.md`, `sleeve-schema-contract.md`, `strategies.md`, `screenshot-ui.md`, `sentiment-signals.md`, `agent-skills.md`.
- [ ] **DB schema** (D-9): `docs/notes-db-schema.md` is **untracked** → `mv docs/notes-db-schema.md docs/reference/db-schema.md` then `git add docs/reference/db-schema.md`. (Generation wiring is step 5; hand-written body stays as a stopgap until then.)
- [ ] **Conventions** — drop `-standard`/`-guide`: `doc-header.md`, `readme-layout.md`, `reference-doc.md`, `python-style.md`. **`naming.md` is untracked** and a stub → overwrite with `staged/naming.md` content and `git add` (don't `git mv`).
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
- [ ] Delete `agentswip/` — **untracked (0 tracked files)** → plain `rm -rf agentswip/` / `Remove-Item -Recurse -Force agentswip` (no `git rm`). Empty placeholders + court-records examples + `generate_maps.py` stub, all superseded/dropped.
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

## Open: track `docs-migration/` or keep it local?

`docs-migration/` is currently gitignored ("# temp"). Options: **(a)** keep ignored — local-only scratch, not in GitHub, lost if the machine fails; **(b)** un-ignore + commit — the plan/record is preserved in history and shareable (matches the original "authoritative living record" intent), at the cost of carrying migration scaffolding in the repo (can be removed post-migration). Decide before/while merging Pass 1.
