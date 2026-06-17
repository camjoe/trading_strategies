# Decision Log

Numbered, append-only record of decisions for the docs consolidation. `D-#` = decided. `D-OPEN-#` = open question awaiting a decision. When an open question is resolved, record the outcome here and update [`proposed-structure.md`](proposed-structure.md) / [`file-mapping.md`](file-mapping.md).

---

## Decided

### D-1 — One source of truth
Consolidate `docs/` and the doc/agent/skill content of `.github/` into a single coherent structure. *Why:* a maintainable, AI-friendly repo needs one place agents can navigate reliably.

### D-2 — CI config stays in `.github/`
`.github/workflows/*.yml` and `.github/dependabot.yml` are out of scope and remain where GitHub requires them.

### D-3 — `.github/app/` removed
Stray untracked Python (`base.py`, `__init__.py`, `account_record_repository.py`) was misplaced; Cameron removed it. No longer a concern.

### D-4 — Resolve structure before moving
Finalize the target structure first; do not move source files until destinations are **Decided**. The original migration prompt is a starting point, not a spec to execute literally.

### D-5 — Move freely; git is the safety net
Renaming or moving files (in `docs/` or anywhere) is fine because everything is tracked. Prefer the easiest path. Prefer moving > rewriting > deleting; never delete information.

### D-6 — Extra scaffold folders kept for now
Retained as possibly-useful; removable later. *(Update: `examples/` folders since dropped per D-OPEN-4; `bots/agents/` kept as the merged agents home per D-OPEN-3.)*

### D-7 — Migration runs in three phases
Consolidation/pruning is separated from the move (see `consolidation.md`):
1. **Pass 0 — Triage** (before move): keep/drop call on each skill/agent/doc; **mark only**, nothing edited/deleted.
2. **Pass 1 — Move**: pure relocation + rename + link-fix; **no content changes** (keeps git diffs reviewable).
3. **Pass 2 — Consolidate** (after move): merge overlaps, freshen, dedupe — easier once everything is unified.
*Why:* mixing moves with edits makes diffs unreviewable; consolidation is easier after relocation. *Tracker:* `consolidation.md` (the Consolidation Report deliverable).

### D-8 — Agent-correctness & quality layer (add A/B/C)
Three additions to make agents/devs apply skills/agents/workflows correctly and hold a consistent quality bar:
- **A. Quality-gates / Definition-of-Done map** → `docs/conventions/quality-gates.md`. One table mapping each rule/convention → its enforcing check (`layer_check`, `ruff`, `mypy`, `pytest`, `readme_check`, `maps_check`) or marking it "advisory, not enforced." Doubles as the DoD every change must pass; tells agents what to self-verify.
- **B. `bots/README.md`** → defines the three surfaces (**skill** = reusable capability; **workflow** = multi-step sequence; **agent** = scoped persona) + a "when to use which" selector. Co-located so anyone entering `bots/` files things correctly.
- **C. Bot authoring standard** → `docs/conventions/bot-authoring.md`. Frontmatter schema every skill/agent must carry (`name`, `when-to-use`, `invoker`, `enforced-by`); good `when-to-use` text is what drives correct agent selection. Extends `skill-invocation-policy`.

*Build timing:* decision now; authored at execution (staged). **D (skills/agents drift-check) NOT adopted now** — deferred, see D-OPEN-11.

### D-9 — DB schema doc: generated block + authored notes
The just-added `docs/notes-db-schema.md` (mis-filed at `docs/` root) → moves to **`docs/reference/db-schema.md`** (reference = "what exists"; drop `notes-` prefix).
- **Single doc, two zones:** a GENERATED schema block (tables/columns/types/indexes) between managed markers, refreshed by extending `scripts/data_ops/describe_db_schema.py` with a markdown write-mode (`--source fresh` = canonical code-defined schema) → **this is the deterministic updater Cameron wanted**; plus an AUTHORED "Semantic notes" section (the `initial_cash` deposit-model note, `note`-prefix conventions, migration rules) the script never touches.
- **Fix the source-of-truth error:** there is **no `trading/database/db.py`** (verified). Real sources are `db_schema.py` (DDL) + `db_migrations.py` (`ColumnMigration`). The doc currently cites `db.py` — correct on migration; generation prevents recurrence.
- **Resolves the AGENTS.md tension:** AGENTS.md warns against a *hand-maintained* schema mirror. Once generated, the markdown is safe — update AGENTS.md's note to point at `docs/reference/db-schema.md`.
- **Readable by agent + human**, deterministic to refresh — the two goals Cameron stated.
- **Build at execution** (script markdown/write mode + first generation). Until then the moved file keeps its current hand-written schema as a stopgap (carries the `db.py` error — fix during migration). Concrete example of "generate the mechanical, author the meaning" (cf. D-OPEN-6).

### D-10 — Execution strategy: in-place `git mv` at root (Strategy A)
The move is executed by reorganizing the live `docs/` and `.github/` directly into final positions with `git mv` (preserves rename history → reviewable diffs), authoring net-new files fresh, then deleting the empty `agentswip/` scaffold. **No physical staging in `agentswip/`** — it was the design sketch, not a waypoint. Commit in labelled per-group chunks; Pass-1 edits limited to mechanical path/link rewrites. *(Fallback Strategy B — assemble in `agentswip/` then promote — rejected: it loses git rename tracking, undermining D-7's diff-legibility goal.)* Full procedure: `execution-runbook.md`. **Status: resolved.**

---

## Open questions

### D-OPEN-1 — Final name for the `agentswip/` root — ✅ RESOLVED
There is **no `agentswip/` folder in the final version.** It is a staging ground only. The final layout promotes its contents to **repo root**: `CLAUDE.md`, `AGENTS.md`, `docs/`, `bots/`, `scripts/`, etc. all sit at repo root. Final destination = the `agentswip/`-prefixed paths in `file-mapping.md` with the `agentswip/` prefix stripped. The current `docs/` is replaced in the process. **Status: resolved.**

### D-OPEN-2 — Do skills/agents move to `bots/`, or stay in `.github/`? — ✅ RESOLVED
Move them. Cameron is fine with breaking default tool discovery — easy to fix manually. **Authoritative copies live in `bots/`** (or their final home). The files in tool-default locations (`.github/skills/`, `.github/copilot-instructions.md`, etc.) become **thin references/duplicates** pointing to the authoritative `bots/` versions. Note the ongoing cost: this introduces a duplication-drift surface (see `focus-areas.md`). **Status: resolved.**

### D-OPEN-3 — Merge `bots/agents/` and `bots/prompts/`? — ✅ RESOLVED
Collapse into a single **`bots/agents/`** folder. `bots/prompts/` is dropped; its persona files (architect, reviewer, refactorer, test-writer) move into `agents/`. **Status: resolved.**

### D-OPEN-4 — How examples are handled — ✅ RESOLVED
**Worked examples embed in the governing doc** (as `doc-header-standard.md` already does). No separate example files, no `examples/` folders. `TEMPLATE.*` blanks stay co-located with what they template.
- **Drop** `docs/examples/` and `bots/skills/examples/` (empty scaffold folders).
- The scaffold's `*-example.md` files are court-records illustrations of *shape* only — they do **not** migrate as content. Listed in `file-mapping.md` as dropped.
- Convention to carry into doc-authoring guidance: if a standard/template needs an example, put it inline; don't create a standalone sample that can drift from its rule. **Status: resolved.**

### D-OPEN-5 — `business-rules/` source of truth — ✅ RESOLVED
The folder **stays** and **`docs/business-rules/` becomes authoritative.** Today the knowledge lives in a couple of JSON files surfaced by the web app — that JSON is Cameron's personal, easy-to-reference tracker, but it is *not* the long-term SoT. Going forward the docs are authoritative because both AI agents and Cameron need one place they can access easily. The JSON becomes **derived/secondary**, not the source.

Consequence (new seam, reversed from before): the web app currently reads the JSON. Once docs are authoritative, the web app must get its data another way — either render the markdown, or **generate the JSON from `docs/business-rules/`**. Decide that when we tackle business-rules. **Status: SoT decided (docs win); transfer + web-app wiring deferred until structure settles.**

### TODO captured
- [ ] Locate the business-rules JSON files (web-app data); **transfer their content into `docs/business-rules/`** as the authoritative version. Do this **after** the rest of the structure is settled.
- [ ] Decide how the web app consumes the now-authoritative docs (render markdown, or generate JSON from docs). Avoid hand-maintaining both.

### D-OPEN-6 — Map freshness tooling — ✅ RESOLVED (design); build deferred to execution
**Approach: drift-check, not generation.** Maps are hybrids — mechanical file-lists (e.g. the `Module` column) interleaved with authored responsibilities + layering rules. Blind generation would clobber the authored content, so instead a script *reports* drift and never writes.

- **What it does:** scan the filesystem, compare against each structural map; report (a) files on disk missing from the map, (b) map entries with no matching file. Read-only.
- **Naming:** drops the `generate_maps.py` idea. New tool, e.g. `scripts/checks/maps_check.py`, following the existing `readme_check.py` / `layer_check.py` idiom; wired into `scripts/run_checks` (advisory, like `readme_check` — flags, doesn't hard-block).
- **Scope:** structural maps only — `trading-package-map.md`, `scripts-map.md`, `ui-map.md`, and `docs-map.md`'s top-level-directory section. **Domain maps (`maps/domains/`) are excluded** — they're purely authored (why things exist), nothing to derive.
- **No `*.generated.md` files, no DO-NOT-EDIT banners.** Maps remain single authored files; the checker validates them. (Updates `proposed-structure.md` maps section.)
- **Relationship to the `update-documentation` skill:** the checker takes over the deterministic "is the inventory current?" job; the AI skill is left for the semantic part (writing/refreshing responsibilities and prose).
- **Scaffold note:** `agentswip/scripts/generate_maps.py` (empty placeholder) is superseded by this; do not migrate it.
- **Build timing:** spec'd now; **build after the migration lands**, so it targets final map paths/format. Tracked as an execution-phase task. A scaffold/generate mode (managed blocks) can be added later if the check proves valuable. **Status: design resolved; implementation deferred.**

### D-OPEN-7 — Unify file-naming convention — ✅ RESOLVED
The convention (to be written into `docs/conventions/naming.md`, currently a stub):

1. **`kebab-case.md` everywhere.** Lowercase, hyphen-separated. Renames the `snake_case` runbooks and the `SCREAMING_SNAKE` `.github` docs.
2. **Reserved UPPERCASE names stay** (tool/convention-mandated): `README.md`, `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `SKILL.md`, `TEMPLATE.*.md`.
3. **Folder conveys type — drop redundant type-prefixes.** `reference/notes-backtesting.md` → `reference/backtesting.md` (the `notes-` prefix goes).
4. **ADRs are numbered:** three-digit `NNN-title.md`, e.g. `adr/001-backtesting-layering.md`. Gives chronological order + a stable `ADR-NNN` id for cross-references. Number reflects acceptance order (provisional numbers in `file-mapping.md` — reorder to match real acceptance dates).
5. **Keep meaningful tool-read suffixes:** `*.agent.md` and `TEMPLATE.*`.
6. **No `-standard`/`-guide`/`-convention` suffix in `conventions/`.** The folder already denotes the file is a standard. So `doc-header-standard.md` → `doc-header.md`, `python-style-guide.md` → `python-style.md`, etc. (The same logic dropped `-guide` from the `governance-review` runbook for consistency.)

Notes: files already in kebab-case need no case change. **Status: resolved.** Next step: write the real `naming.md` (drafted in `staged/naming.md`).

### D-OPEN-9 — Style-guide consolidation
Review the style guides together at a later time: `python-style.md` (formerly `python-style-guide.md`) and `.github/BOT_STYLE_GUIDE.md` (would become `bot-style.md`). Question: do they merge into one style guide, or stay separate? Cameron wants to review them — including the Python one — together in a future pass. Until then, `bot-style` placement/name stays parked. **Status: open (deferred by choice).**

### D-OPEN-10 — Internal link rewriting on rename/move
Docs cross-link each other by relative path (e.g. `doc-header-standard.md`'s `Related:` line points at `reference-doc-standard.md`, `readme-layout-standard.md`; `docs/README.md` and `docs-map.md` link dozens of files). Every rename/move in `file-mapping.md` breaks these links. **Action at execution time:** after moving, sweep all docs for stale relative links and the doc-header `Related:` lines, and update them. Consider a link-check step. **`AGENTS.md` is the heaviest case** — it's dense with `.github/...` paths (skills, agents, BOT_*.md) that all move under D-OPEN-2; budget real time to rewrite it. **Status: open — execution-phase task, tracked so it isn't forgotten.**

### D-OPEN-11 — Agent self-verification tooling (deferred, future viability)
Considered but not adopted now (from the structure evaluation):
- **Skills/agents drift-check + generated catalog** — a `maps_check` sibling validating AGENTS.md routing ↔ actual `bots/skills` + `bots/agents` on disk, so routing can't silently lie. Same generator produces the human-readable catalog the `help/` skill presents (one source = `when-to-use` frontmatter; views = help catalog, AGENTS routing, auto-trigger). See `consolidation.md` note D1. Strong future-viability item; revisit after the move and after `maps_check.py` proves the pattern.
- **Skill evals** — automated tests that a skill triggers/behaves correctly. State-of-the-art but premature; note for later.
**Status: deferred by choice.**

### D-OPEN-12 — Agent understanding/use of `scripts/` (deferred, post-move)
Goal: agents understand and correctly use `scripts/` (auto-trading runners, `screenshot_ui`, etc.) — for skills and for discussion with Cameron.
- **Structure already supports this** — no new folders needed: `docs/maps/scripts-map.md` (catalog: what each script does + when to use), `docs/runbooks/` (operational how-to, e.g. daily auto-trading), `docs/reference/notes-screenshot-ui.md` (subsystem detail).
- **Pass-2 / post-move task:** (a) make `scripts-map` rich enough on usage + safety; (b) cross-link operational scripts to the skills/agents that drive them (e.g. `screenshot_ui` ↔ a UI-verify skill; auto-trading runners ↔ `trading-runtime` agent + runbooks); (c) consider a skill wrapping screenshot-for-change-confirmation if it recurs.
- Cameron flagged this as likely post-move. **Status: deferred by choice.**

### D-OPEN-8 — Root AI entrypoints — ✅ RESOLVED
Reality check: only 3 entrypoints exist today (`README.md`, `AGENTS.md`, `CLAUDE.md`); `copilot-instructions.md`/`CONTRIBUTING.md` are only empty scaffold placeholders.

- **`AGENTS.md` is canonical** — the single AI-instructions source of truth (already the richest doc).
- **`CLAUDE.md` becomes thin** — imports AGENTS.md via Claude Code `@AGENTS.md` syntax + any Claude-only note. Its current "Docs Folder Guide" duplicates `docs/README.md` — drop the duplication; link to `docs/README.md` instead.
- **`.github/copilot-instructions.md`** (Copilot **is** used) — create as a thin redirect → `AGENTS.md`. Lives in `.github/` (where Copilot reads it), not repo root.
- **`README.md`** stays as-is — the human front door, distinct from the above.
- **`CONTRIBUTING.md`** — author a real one at repo root (human contributor workflow: setup, test/lint/migration commands, PR expectations), distinct from README's overview. To be drafted (staged).
- Scaffold copies (`agentswip/CLAUDE.md`, `AGENTS.md`, `copilot-instructions.md`, `README.md`, `CONTRIBUTING.md`) are empty/placeholder → superseded by the real root files; do not migrate.

**Status: resolved.** Authoring of the thin CLAUDE.md, copilot-instructions.md, and the real CONTRIBUTING.md is execution-phase work (staged when written).
