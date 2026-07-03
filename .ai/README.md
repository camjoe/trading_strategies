# AI

Type: index
Status: Active
Created: 2026-06-17
Last Reviewed: 2026-07-02
Purpose: Define the skills surface — the repo's single reusable task surface — and how it is routed and discovered.
Related: [AGENTS.md](../AGENTS.md), [Skill Invocation Policy](../docs/reference/skill-invocation-policy.md)

## Overview

Operational assets for AI agents working in this repo. **[`AGENTS.md`](../AGENTS.md)** (repo root)
is the canonical entrypoint and routing guide; this folder holds the **skills** it routes to
(`.ai/skills/<skill>/`, each with a `SKILL.md` entrypoint plus on-demand reference files).

Repo-specific `.agent.md` personas were retired 2026-07-02: their safety content lives in the
skills and `docs/architecture/architecture-conventions.md`; their routing lives in `AGENTS.md`.

## Usage

- Default to the most specific matching skill — see the routing table in [`AGENTS.md`](../AGENTS.md).
- Project-only safety rules (live-trading guard, migration rules, layer boundaries) live in
  `docs/architecture/architecture-conventions.md` and apply in every session, skill or not.
- Authoring a new skill? Use the `create-skill` skill and follow the authoring rules in
  [`.ai/skills/README.md`](skills/README.md); invocation rules are in
  [`skill-invocation-policy.md`](../docs/reference/skill-invocation-policy.md).

## Discoverability

The `help/` skill catalogs what's available by enumerating `.ai/skills/*/SKILL.md` from disk;
routing lives in `AGENTS.md`. Both should derive from each skill's `description` (WHAT + WHEN)
frontmatter — see the authoring rules in [`.ai/skills/README.md`](skills/README.md) — so they
can't drift from what's on disk.
