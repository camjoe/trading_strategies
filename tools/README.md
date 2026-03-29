# Tools

Top-level tooling integrations and submodules.

## Project Manager

`project_manager/` contains the planning dashboard and commit-context tooling.

For commit-context usage and documentation precheck details, see:
- `tools/project_manager/README.md`

Repository note:

- `tools/project_manager/` is a git submodule, so structure or workflow changes inside that area can make the top-level `tools/` area appear stale until this README or submodule docs are updated alongside the submodule state.
- A dirty submodule pointer in the workspace is enough to trigger top-level `tools/` docs freshness, even when no top-level Python tooling file changed.

Recent tooling note:

- `tools/project_manager/scripts/generate_commit_context.py` now references `scripts/check_docs_freshness.py` as the CI docs-freshness gate entrypoint.

Additional workflow notes:

- `python -m scripts.ci_smoke` is the primary local audit command mirroring CI core checks.
- Trading structure guidance is tracked in `docs/architecture/trading-module-boundaries.md`.
- Low-coverage runtime follow-up notes and a ready-to-use testing prompt are tracked in `docs/architecture/runtime-job-coverage-follow-up.md`.
- Runtime data operations use canonical module entrypoints under `trading/interfaces/runtime/data_ops/`.
- Repository-backed backend abstraction updates should keep focused validation in `tests/trading` and `tests/paper_trading_ui/backend` aligned.
- Repository extraction slices in `trading/` should include focused profile/reporting tests when account update/list paths are touched.
