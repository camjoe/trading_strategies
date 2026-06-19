# Focus Areas — Where Your Energy Pays Off

Candid, opinionated assessment of the migration's parts: which are cosmetic, which are real engineering, and where you'll likely need to keep improving after the structure lands. Updated as we learn more. Direct by request — push back if you disagree.

**Effort** = work to do it once. **Value** = payoff for a maintainable, AI-friendly repo over years. **Ongoing?** = needs sustained discipline, not a one-time fix.

## The big picture

The folder shuffle is the *easy, low-value* part — satisfying but mostly cosmetic. The durable value is in **three things that fight documentation rot**: deterministic map generation, doc-header/staleness discipline, and not letting duplicated copies drift. Spend your energy there.

## Scorecard

| Item | Effort | Value | Ongoing? | Verdict |
|---|---|---|---|---|
| **Generated DB schema doc (D-9)** | Low | ⭐⭐⭐⭐ | Yes | Extend `describe_db_schema.py` to write the schema block of `docs/reference/db-schema.md`; authored notes stay manual. Already-present `db.py` error proves the hand-maintained-mirror risk. High value, low effort — a clean "generate the mechanical" win. |
| **Map drift-check (`scripts/checks/maps_check.py`)** | Medium | ⭐⭐⭐⭐⭐ | Yes | **The single highest-leverage thing here.** Maps rot fastest; a drift-checker (D-OPEN-6 — scan FS, report missing/extra, never writes) is what keeps the SoT trustworthy without clobbering authored responsibilities. Lower effort than full generation, nearly all the value. Build after migration; wire into `run_checks`. |
| **Doc-header + staleness discipline** | Low each, High cumulative | ⭐⭐⭐⭐ | Yes | Your `Type/Status/Last Reviewed` headers + "goes stale when" columns are gold — but only if you keep applying them. A habit to build, not a task to finish. |
| **Avoiding duplication drift** (bots↔.github redirects; business-rules↔JSON) | Medium | ⭐⭐⭐⭐ | Yes | Every duplicated copy is a future inconsistency. Keep copies *thin* (pointers) or *generated*, never hand-maintained twins. The risk you'll fight for months. |
| **Quality-gates / DoD map (D-8 A)** | Low–Med | ⭐⭐⭐⭐ | Yes | Maps each rule → its enforcing check (or "advisory"); the Definition of Done. Turns conventions into something agents can self-verify. High leverage for consistent quality. |
| **bots/README (D-8 B)** | Low | ⭐⭐⭐ | Slightly | Defines skill/workflow/agent surfaces at the bots/ root. (D-8 A/C — quality-gates + bot-authoring — dropped as redundant with existing skills/guides; advisory-vs-enforced folded into validate-code.) |
| **business-rules: docs authoritative, JSON derived** | Medium | ⭐⭐⭐ | Partly | SoT decided: `docs/business-rules/` wins; web-app JSON becomes derived. Real work = transfer content in, then wire the web app to render docs or generate JSON from them. Deferred until structure settles. |
| Renaming `agentswip/` → repo root | Trivial | ⭐ | No | Must-do, but cosmetic. No skill required. |
| Merge `agents/` + `prompts/` | Low | ⭐⭐ | No | Organizational clarity; one-time. |
| Drop `examples/` → use `TEMPLATE.*` | Low | ⭐⭐ | No | Removes a future dumping ground. One-time cleanup. |
| Unify file-naming convention | Low–Med | ⭐⭐ | Slightly | Cheapest to do during the move. Mild ongoing discipline to keep consistent. |
| Root entrypoint dedup (AGENTS canonical) | Medium | ⭐⭐⭐ | Yes | ✅ Decided (D-OPEN-8): AGENTS.md canonical; CLAUDE.md + .github/copilot-instructions.md thin redirects; README human; new CONTRIBUTING. Ongoing discipline: keep redirects thin, don't re-bloat. AGENTS.md is also the heaviest file to path-rewrite at execution. |

## Where you'll likely need to grow (next few months)

1. **Resisting "AI loves one giant file."** Your own README names this. The structure helps, but the pull toward dumping everything into CLAUDE.md/AGENTS.md is constant. Keep entrypoints thin and push content into `docs/`.
2. **Treating generation as the default for anything mechanical.** Maps today; consider it for parts of reference and business-rules. If a human/agent has to remember to update it, it will rot. If a script makes it, it stays true.
3. **Owning the duplication seams.** Two you've consciously created — `.github/` thin-redirects → `bots/`, and `docs/business-rules/` (authoritative) vs the web-app JSON (now derived) — are the most likely sources of "the docs lied to me" six months out. SoT is decided for both; the work is making the *other* side genuinely derived (a generator or a pointer), never a hand-maintained twin.
4. **Doc-header discipline at creation time.** Cheap when you write the file, expensive to retrofit. The staleness tooling is only as good as the headers feeding it.

## Items to revisit once structure is done

- [ ] Build `scripts/checks/maps_check.py` (drift-check, read-only); wire into `run_checks` advisory.
- [ ] Transfer business-rules JSON content into authoritative `docs/business-rules/`; then wire the web app to render docs or generate JSON from them.
- [ ] Define the thin-redirect pattern for `.github/skills` + `copilot-instructions.md` (what exactly a "pointer" file contains).
- [ ] Pick and document the one file-naming convention; apply during moves.
