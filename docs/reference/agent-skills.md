# Agent Skills — Authoring Guide (Pointer)

Type: notes
Status: Active
Created: 2026-06-13
Last Reviewed: 2026-07-02
Purpose: Pointer to the upstream skill-authoring guidance plus the handful of principles this repo leans on — replaces a full verbatim copy of the upstream docs.
Related: [Skill Invocation Policy](skill-invocation-policy.md), [Docs Map](../maps/docs-map.md)

This file used to hold a full copy (~1,100 lines) of Anthropic's skill-authoring documentation.
The copy could only drift from upstream and dominated the docs corpus, so it is now a pointer.

## Where the guidance lives

- **Upstream authoring guide:** <https://www.claudeskills.org/docs/agent-skills/overview>
  (concepts) and its best-practices pages — the authoritative source the old copy came from.
- **Repo-specific rules** (layout, naming, localization, inventory): [`.ai/skills/README.md`](../../.ai/skills/README.md).
- **Authoring workflow:** use the `create-skill` skill (`.ai/skills/create-skill/SKILL.md`);
  improving an existing skill uses `update-skill`.
- **Who may invoke what:** [skill-invocation-policy.md](skill-invocation-policy.md).

## The principles this repo actually leans on

The upstream guide is long; these are the rules our skills are reviewed against:

1. **Concise is key.** The context window is shared. Assume the model is already smart — only add
   context it doesn't have. Every SKILL.md paragraph must justify its token cost.
2. **Progressive disclosure.** Keep SKILL.md as the entry point; push mode- or domain-specific
   detail into sibling reference files loaded on demand (this repo's folder-based skill layout).
3. **Match freedom to fragility.** Give text instructions for judgment tasks; give exact commands
   or scripts for fragile, deterministic steps (validation commands, file paths).
4. **Test with real usage.** A skill's description decides whether it triggers — write it from the
   user's task vocabulary, not the skill's internals, and iterate on real invocations.
