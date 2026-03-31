# Tools

Top-level tooling integrations and submodules.

## Purpose

Describe shared tooling surfaces and where to find setup and operational guidance for packaged subtools.

## Project Manager

`project_manager/` contains the planning dashboard and commit-context tooling.

For commit-context usage and documentation precheck details, see:
- `tools/project_manager/README.md`

Recent tooling note:

- `tools/project_manager/scripts/generate_commit_context.py` provides commit-context summaries and documentation precheck guidance.

Additional workflow notes:

- `python -m scripts.run_checks --profile ci` is the primary local audit command mirroring CI core checks.
- Trading structure guidance is tracked in `.github/BOT_ARCHITECTURE_CONVENTIONS.md`.
- Runtime data operations use canonical module entrypoints under `trading/interfaces/runtime/data_ops/`.
- Repository-backed backend abstraction updates should keep focused validation in `tests/trading` and `tests/paper_trading_ui/backend` aligned.
- Repository extraction slices in `trading/` should include focused profile/reporting tests when account update/list paths are touched.

## Workflows

1. Use this README as the entrypoint for tooling ownership and documentation links.
2. Follow `tools/project_manager/README.md` for project-manager runtime operations.
3. Run repository-wide smoke checks with `python -m scripts.run_checks --profile ci` after tooling-related changes.
