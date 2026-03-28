# Tools

Top-level tooling integrations and submodules.

## Project Manager

`project_manager/` contains the planning dashboard and commit-context tooling.

For commit-context usage and documentation precheck details, see:
- `tools/project_manager/README.md`

Recent tooling note:

- `tools/project_manager/scripts/generate_commit_context.py` now references `scripts/check_docs_freshness.py` as the CI docs-freshness gate entrypoint.

Additional workflow notes:

- `python -m scripts.ci_smoke` is the primary local audit command mirroring CI core checks.
- Trading structure guidance is tracked in `docs/architecture/trading-module-boundaries.md`.
- Low-coverage runtime follow-up notes and a ready-to-use testing prompt are tracked in `docs/architecture/runtime-job-coverage-follow-up.md`.
- Runtime data operations use canonical module entrypoints under `trading/interfaces/runtime/data_ops/`.
- Repository-backed backend abstraction updates should keep focused validation in `tests/trading` and `tests/paper_trading_ui/backend` aligned.
