---
name: docs-check
description: Passively checks whether documentation is stale relative to the current branch diff. Always advisory — never blocks the workflow.
---

# Docs Check

A passive staleness check. Does not update docs — reports only. Any findings surface in the PR readiness report as advisory items.

## Command

```
python -m scripts.checks.readme_check
```

Reports README files that have not been updated within the staleness threshold. Review its output alongside the branch diff.

## What to check manually

After running `readme_check`, scan the diff for:

1. **Path changes** — were any files moved or renamed? Are those paths still accurate in READMEs, AGENTS.md, or other docs?
2. **Command changes** — were any CLI commands, scripts, or entrypoints changed? Are the docs examples still correct?
3. **Workflow changes** — were any job schedules, feature flags, or operational procedures changed? Are the corresponding docs updated?
4. **New public surfaces** — does a new service, route, or script exist without any documentation?

<!-- TODO: create docs/maps/source-to-docs-map.md — a map of source directories to their owning documentation files to make this check deterministic -->

## Severity

Always **ADVISORY**. Docs staleness never blocks a PR. Surface findings in the readiness report so the user can decide whether to sync docs before or after merging.

## Repo references

- `scripts/checks/readme_check.py`
- `AGENTS.md`
- `.github/DOCS_PRECOMMIT_POLICY.md`
