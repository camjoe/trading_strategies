# TODO

Backlog for evolving this project from local research scripts into a more robust strategy platform.

## Near Term

- [ ] Define MVP scope for paper trading lifecycle (account creation, trades, reporting, snapshots).
- [ ] Add CSV export for `compare-strategies` output.
- [ ] Add tests for trade accounting edge cases (fees, partial exits, invalid sells).
- [ ] Add validation for data quality gaps and missing prices.

## Data and Storage

- [ ] Evaluate moving from SQLite to PostgreSQL for multi-user and larger historical datasets.
- [ ] Draft schema migration plan (SQLite -> PostgreSQL) for `accounts`, `trades`, and `equity_snapshots`.
- [ ] Add database abstraction layer (repository/service pattern) to reduce SQL coupling.
- [ ] Consider managed Postgres options (local Docker, Supabase, Railway, Render, Neon).

## Framework and App Architecture

- [ ] Evaluate whether Django is needed for a web dashboard/API and user auth.
- [ ] Compare Django vs FastAPI for API-first architecture.
- [ ] Decide on project structure if framework is introduced:
  - `app/` service layer
  - `db/` migrations/models
  - `api/` endpoints
  - `jobs/` scheduled snapshots/backfills

## ML / Statistical Modeling Expansion

- [ ] Define first ML use case (classification of next-day direction, return regression, or regime detection).
- [ ] Add feature store patterns for technical + fundamental + macro features.
- [ ] Evaluate PyTorch for custom deep models and sequence models.
- [ ] Evaluate TensorFlow/Keras for production deployment tooling.
- [ ] Add experiment tracking (MLflow or Weights & Biases).
- [ ] Add model validation standard (walk-forward CV, leakage checks, calibration diagnostics).

## Ops and Reliability

- [ ] Add scheduled jobs for daily snapshot capture.
- [ ] Add structured logging and error tracking.
- [ ] Add environment-based settings management (`.env`, config module).
- [ ] Add CI checks for linting/tests.

## Decision Questions

- [ ] At what account/data scale should PostgreSQL replace SQLite?
- [ ] Do we need a web app (Django) now, or should we stay script-first for speed?
- [ ] Which ML stack should be primary for first production candidate model?
