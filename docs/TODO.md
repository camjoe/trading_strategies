# TODO

Backlog for evolving this project from local research scripts into a more robust strategy platform.

## Near Term

- [ ] Add CSV export for `compare-strategies` output.

- [ ] Add database abstraction layer (repository/service pattern) to reduce SQL coupling.

## ML / Statistical Modeling Expansion

- [ ] Define first ML use case (classification of next-day direction, return regression, or regime detection).
- [ ] Add feature store patterns for technical + fundamental + macro features.
- [ ] Evaluate PyTorch for custom deep models and sequence models.
- [ ] Evaluate TensorFlow/Keras for production deployment tooling.
- [ ] Add experiment tracking (MLflow or Weights & Biases).
- [ ] Add model validation standard (walk-forward CV, leakage checks, calibration diagnostics).

## Ops and Reliability

- [ ] Add scheduled jobs for daily snapshot capture.

## Add OOP
- [] Database abstraction layer, Strategy (for easier creation), and abstraction for retrieveing data (yfinance, crypto)

## Backlog
- [ ] Add first strategy hypothesis
- [ ] Define baseline benchmark
- [ ] Define success criteria for first test