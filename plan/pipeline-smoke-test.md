# Plan: pipeline smoke test (throwaway)

Status: in progress (branch `feature/pipeline-smoke-test`). Before pickup: drafted 2026-10-12.
Throwaway: it exists only to exercise `implement-plan --container --agent-container` once more, with
the agent denied everything outside its allow list; delete it and its branch afterwards.

Branch to use: `feature/pipeline-smoke-test`

## Goal
Add a small direct unit test for `claimed_status` in `scripts/forge/plans.py`, which is only covered indirectly today,
using a commit, a rename, and a removal so the agent's file and git commands are all exercised. Nothing about the
behavior changes.

## Work
1. First commit: in the `tests/scripts` directory create a scratch note named `pipeline_smoke_scratch.txt` containing
   the word scratch, and a test file named `test_pipeline_smoke_draft.py` with exactly two tests of
   `claimed_status(branch, previous)`:
   - `claimed_status("feature/x", "drafted")` returns ``"in progress (branch `feature/x`). Before pickup: drafted"``.
   - `claimed_status("feature/x", "")` returns ``"in progress (branch `feature/x`). Before pickup:"`` (no trailing space).
   Follow `docs/conventions/python-style.md`: type hints on the test functions, no comments or docstrings.
   Commit as `test(forge): draft the claimed_status tests`.
2. Second commit: rename the test file to `test_pipeline_smoke.py` with `git mv`, and remove the scratch note with
   `git rm`. Commit as `test(forge): cover claimed_status directly`.
3. Run `.venv/bin/python -m pytest tests/scripts -k pipeline_smoke -q --no-cov`, then `python -m scripts.fix_checks`
   and `python -m scripts.run_checks pr --base origin/develop`. Fix anything they report in your own work and commit it.
   If a command you need is refused, do not work around it: write what was refused to the questions file.

## Not in scope
- Any change under `scripts/` (it is a guarded path), any other test file, any documentation.
- Editing this plan, the plan index, or deleting this plan.

## Verification
- The branch's final tree differs from its start only by one new file, `test_pipeline_smoke.py` in `tests/scripts`,
  with two passing tests; the scratch note and the draft-named file are gone.
