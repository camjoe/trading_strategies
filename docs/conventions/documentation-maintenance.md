# Documentation Maintenance

Type: convention
Status: Active
Created: 2026-06-24
Last Reviewed: 2026-07-13
Purpose: The durable habits that fight documentation rot and the principles behind the repo's docs drift-check tooling.
Related: [Documentation Authoring Standard](docs-authoring.md), [File Naming Convention](naming.md), [General Style](general-style.md), [Docs Map](../maps/docs-map.md)

## Principles

The folder/file shuffle is the easy, low-value part of keeping docs healthy. The durable value is in the habits below — spend energy here.

1. **Keep entrypoints thin.** The pull toward dumping everything into `CLAUDE.md` / `AGENTS.md` is constant. Push content into `docs/`; keep the redirects and imports thin (`CLAUDE.md` imports `@AGENTS.md`; `.github/copilot-instructions.md` redirects to `AGENTS.md`). `README.md` stays the human front door.

2. **Generate or check the mechanical.** If a human or agent must *remember* to update something, it rots. Mechanical inventories (directory maps, DB schema reference, internal links, README freshness) are drift-checked or generated, never hand-maintained — the docs drift checkers under `scripts/checks/docs/` (`maps_check`, `link_check`, `db_schema_check`, `readme_check`) follow one pattern: the script verifies *the mechanical* (every file on disk appears in the map; every map row has a file; every link resolves), and humans author *the meaning* (responsibilities, prose).

3. **Own the duplication seams.** Every consciously duplicated piece of information is a "the docs lied to me" risk. Two known seams: the `.github/` redirects → `AGENTS.md`/`.ai/`, and the in-app docs content (`scripts/documentation_ui/` sources, authoritative) vs the generated frontend JSON assets (derived via `python -m scripts.documentation_ui.sync`). Make the *other* side genuinely derived (a generator or a pointer), never a hand-maintained twin.

4. **Doc-authoring discipline at creation time.** `Type` / `Status` / `Last Reviewed` headers and "goes stale when" columns are cheap to add when writing a file and expensive to retrofit — and the staleness tooling is only as good as the headers feeding it. See [Documentation Authoring Standard](docs-authoring.md).

Implemented enforcement lives in `scripts/checks/`, `scripts/documentation_ui/check.py`, and the
`static-checks` job in `.github/workflows/ci.yml`; see
[`scripts-map.md`](../maps/scripts-map.md) for the current inventory.
