# Task Prompt: Cleanup Long Files

## Task Metadata
- Task ID: `pm-tasks-items-cleanup-long-files`
- Title: `Cleanup Long Files`
- Source Board: `Tasks`
- Workspace: `Trading App`
- Severity: `high`
- Mode: `single`
- Execution Intent: `research`
- Base Branch: `feature`
- Description Step Focus: `Step 1`

## Objective
Research options to reduce long import blocks and identify opportunities to simplify parameter passing/value reuse through classes or models, without changing runtime behavior.

## Task Type
- `research`

## Constraints
- Do not change runtime behavior.
- Keep recommendations grounded in current repository architecture.
- Prefer incremental approaches over broad rewrites.
- Do not perform destructive git actions.

## Acceptance Criteria
- Identify representative files with long/complex import sections.
- Evaluate practical import-shortening approaches and tradeoffs.
- Evaluate class/model encapsulation opportunities and tradeoffs.
- Provide concrete recommendations for `should do` and `could do` for Step 2.
- Include validation commands and outcomes relevant to this research-only run.

## Assigned Agent
- `Project Structure Steward`

## Required Files
- `tools/project_manager/data/project_db.json`
- `trading/**`
- `paper_trading_ui/backend/**`
- `paper_trading_ui/frontend/src/**`
- `docs/architecture/**`

## Validation Checklist
- [x] Confirm task-to-query match confidence is high.
- [x] Capture findings for imports and encapsulation opportunities.
- [x] Ensure recommendations preserve behavior and layering boundaries.
- [x] Record commands run and outcomes.
- [x] Write result file in `docs/sprint/task_results/`.
