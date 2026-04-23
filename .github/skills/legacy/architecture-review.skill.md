---
name: Architecture Review
layer: portable
description: Portable starter skill for enforcing layering, dependency direction, and module ownership in application repositories.
use_when:
  - reviewing new modules or major refactors
  - checking import direction or package placement
  - auditing whether logic lives in the correct layer
localize_with:
  - architecture rules document
  - package ownership map
  - allowed dependency directions
---

## Goal

Keep code changes aligned with the repository's architecture instead of only making the diff work locally.

## Responsibilities

1. Classify each changed module by responsibility.
2. Check dependency direction and import boundaries.
3. Flag logic that belongs in a lower or higher layer.
4. Recommend the correct placement for new code.

## Constraints

1. Do not focus on style unless it affects architecture clarity.
2. Do not approve direct boundary violations just because tests pass.
3. Do not assume every repo uses the same layer names.

## Localize for a project

Fill in:

- the repo's architecture conventions document
- the allowed layer flow
- the canonical folders for interfaces, services, domain, persistence, and UI

## Expected output

1. Boundary summary
2. Violations or risks
3. Correct target layer for each questionable change
4. Suggested follow-up bot or skill
