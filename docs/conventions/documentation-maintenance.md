# Documentation Maintenance

Type: convention
Status: Active
Created: 2026-06-24
Last Reviewed: 2026-07-02
Purpose: The durable habits that fight documentation rot, plus the deferred doc-tooling work they motivate. These principles are the *why* behind the repo's drift-check tooling (`maps_check`, `link_check`, `db_schema_check`, `readme_check`).
Related: [Documentation Authoring Standard](docs-authoring.md), [File Naming Convention](naming.md), [General Style](general-style.md), [Docs Map](../maps/docs-map.md)

## Principles

The folder/file shuffle is the easy, low-value part of keeping docs healthy. The durable value is in the habits below — spend energy here.

1. **Keep entrypoints thin.** The pull toward dumping everything into `CLAUDE.md` / `AGENTS.md` is constant. Push content into `docs/`; keep the redirects and imports thin (`CLAUDE.md` imports `@AGENTS.md`; `.github/copilot-instructions.md` redirects to `AGENTS.md`). `README.md` stays the human front door.

2. **Generate or check the mechanical.** If a human or agent must *remember* to update something, it rots. Mechanical inventories (directory maps, DB schema reference, internal links, README freshness) are drift-checked or generated, never hand-maintained — the drift checkers under `scripts/checks/` (`maps_check`, `link_check`, `db_schema_check`, `readme_check`) follow one pattern: the script verifies *the mechanical* (every file on disk appears in the map; every map row has a file; every link resolves), and humans author *the meaning* (responsibilities, prose).

3. **Own the duplication seams.** Every consciously duplicated piece of information is a "the docs lied to me" risk. Two known seams: the `.github/` redirects → `AGENTS.md`/`.ai/`, and the in-app docs content (`scripts/documentation_ui/` sources, authoritative) vs the generated frontend JSON assets (derived via `python -m scripts.documentation_ui.sync`). Make the *other* side genuinely derived (a generator or a pointer), never a hand-maintained twin.

4. **Doc-authoring discipline at creation time.** `Type` / `Status` / `Last Reviewed` headers and "goes stale when" columns are cheap to add when writing a file and expensive to retrofit — and the staleness tooling is only as good as the headers feeding it. See [Documentation Authoring Standard](docs-authoring.md).

## Deferred improvements

Tracked backlog of doc-tooling work that applies the principles above. Each is self-contained; none is started.

- **In-app docs seam audit** (principle 3). The in-app doc assets (`api.json`, `software.json`, `finance.json`) are generated from `scripts/documentation_ui/` sources via `sync.py`. Periodically verify the generated JSON is never hand-edited (e.g. a check that regenerating produces no diff), so the seam stays genuinely derived.
- **Skills/agents drift-check + generated `help/` catalog** (principle 2). Add a `maps_check` sibling that validates `AGENTS.md` routing against the actual `.ai/skills/` + `.ai/agents/` so routing can't silently lie, and generate a `help/` catalog from each skill/agent's `when-to-use` frontmatter (one source feeding help catalog + routing). Push (auto-trigger / routing) beats pull (remembering to run `help`).
- **Doc-header lint** (principles 2 and 4). Add an advisory check (sibling of `link_check`) that
  verifies every `docs/` file carries the six header fields with valid `Type`/`Status` vocabulary
  per [docs-authoring.md](docs-authoring.md) — catches the missing-`Last Reviewed` class of drift
  permanently.
- **Scripts discoverability** (principles 1–2). Enrich [`docs/maps/scripts-map.md`](../maps/scripts-map.md) with per-script usage + safety notes, and cross-link operational scripts to the skills/agents that drive them (e.g. UI screenshot tooling ↔ a UI-verify skill; auto-trading runners ↔ the `trading-runtime` agent + runbooks).
