---
name: Deep Code Review
layer: portable
description: Portable starter skill for whole-area code health audits focused on simplification, stale-code detection, redundancy removal, schema relevance, and architecture quality.
use_when:
  - auditing a mature codebase for simplification and consolidation opportunities
  - reviewing a subsystem beyond the current diff
  - looking for stale, superseded, duplicated, or overly complex code
localize_with:
  - architecture rules and package ownership
  - canonical schema or migration references
  - validation commands for backend and frontend
---

## Goal

Perform a deep, read-only audit of a code area to identify how to make it smaller, simpler, clearer, and more maintainable without weakening behavior or safety.

## Responsibilities

1. Identify duplication, near-duplication, and common logic that should be extracted.
2. Detect stale, superseded, rarely used, or parallel implementations that may be candidates for consolidation or removal.
3. Review architecture quality, abstraction boundaries, modularity, and human readability.
4. Check whether schema elements, data paths, and feature surfaces still appear justified by current code usage.
5. Surface opportunities to reduce line count, dependency count, branching complexity, and one-off special cases.

## Review dimensions

1. **Simplification** — places where the same behavior can be preserved with less code or fewer layers.
2. **Redundancy** — duplicate helpers, repeated workflows, or slightly divergent parallel implementations.
3. **Stale or superseded code** — older paths that appear replaced by newer canonical flows.
4. **Generalization opportunities** — specialized logic that could be folded into a shared abstraction.
5. **Schema relevance** — tables, columns, or data paths that may no longer justify their maintenance cost.
6. **Canonical-path drift** — older call paths that bypass newer canonical modules, services, or adapters.
7. **Config/default drift** — duplicated defaults, seeded values, or config sources that can silently diverge.
8. **Surface overlap** — the same workflow implemented in multiple surfaces with slightly different rules.
9. **Architecture quality** — layering, ownership, abstraction boundaries, dependency direction, and modularity.
10. **Human legibility** — naming, flow clarity, cohesion, and whether a teammate can follow the design quickly.

## Constraints

1. Keep the review read-only and evidence-based.
2. Do not recommend deleting a feature, schema element, or code path without citing the relevant usage evidence or uncertainty.
3. Do not optimize for line-count reduction alone when it would hide intent or weaken safety.
4. Do not collapse meaningful abstractions just because they add files; prefer simpler systems, not merely fewer modules.
5. Separate high-confidence candidates from hypotheses that need runtime or product confirmation.
6. Classify recommendations by confidence and action type, not just by severity.

## Localize for a project

Fill in:

- exact folders to review first
- architecture conventions document
- schema or migration reference files
- validation commands for Python, frontend, and repository-wide checks
- project-specific safety constraints that must not be weakened

## Expected output

1. Scope and review method
2. Simplification and code-reduction opportunities
3. Redundant/common-code extraction opportunities
4. Stale or superseded code and feature paths
5. Schema/table/column relevance review
6. Canonical-path and config/default drift findings
7. Layering, abstraction, and dependency findings
8. Prioritized remediation roadmap with confidence notes and action labels
