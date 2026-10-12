# Plan: pipeline smoke test (throwaway)

Status: drafted 2026-10-12. Throwaway: it exists only to exercise `implement-plan --container --agent-container` once; delete it and its branch afterwards.

Branch to use: `feature/pipeline-smoke-test`

## Goal
Add a small direct unit test for `claimed_status` in `scripts/forge/plans.py`, which is only covered indirectly today.
Nothing about the behavior changes.

## Work
1. Create the file `test_pipeline_smoke.py` in the `tests/scripts` directory with exactly two tests of `claimed_status(branch, previous)`:
   - `claimed_status("feature/x", "drafted")` returns ``"in progress (branch `feature/x`). Before pickup: drafted"``.
   - `claimed_status("feature/x", "")` returns ``"in progress (branch `feature/x`). Before pickup:"`` (no trailing space).
2. Follow `docs/conventions/python-style.md`: type hints on the test functions, no comments or docstrings.
3. Run the new tests with `.venv/bin/python -m pytest tests/scripts -k pipeline_smoke -q --no-cov`, then
   `python -m scripts.fix_checks` and `python -m scripts.run_checks pr --base origin/develop`.
4. Commit once as `test(forge): cover claimed_status directly`.

## Not in scope
- Any change under `scripts/` (it is a guarded path), any other test file, any documentation.
- Editing this plan, the plan index, or deleting this plan.

## Verification
- `test_pipeline_smoke.py` exists in `tests/scripts` with two passing tests and the commit touches only that file.
