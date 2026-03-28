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
- Trading structure planning notes are tracked in `docs/architecture/trading-structure-migration-plan.md`.
