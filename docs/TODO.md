# TODO

Backlog for evolving this project from local research scripts into a more robust strategy platform.

## Near Term

- [ ] Add CSV export for `compare-strategies` output.
- [ ] Add database abstraction layer (repository/service pattern) to reduce SQL coupling.

## Completed Milestones

- [x] Phase 1: Backtest leaderboard and batch comparison commands.
- [x] Phase 2: Strategy registry/spec abstraction and expanded technical strategy set.
- [x] Phase 3: Proxy feature seam plus topic and macro proxy strategies.
- [x] Phase 4: Scheduled strategy rotation persistence and auto-trader integration.

## ML / Statistical Modeling Expansion

- [ ] Define first ML use case (classification of next-day direction, return regression, or regime detection).
- [ ] Add feature store patterns for technical + fundamental + macro features.
- [ ] Evaluate PyTorch for custom deep models and sequence models.
- [ ] Evaluate TensorFlow/Keras for production deployment tooling.
- [ ] Add experiment tracking (MLflow or Weights & Biases).
- [ ] Add model validation standard (walk-forward CV, leakage checks, calibration diagnostics).

## Ops and Reliability

- [ ] Add scheduled jobs for daily snapshot capture.

## Docs Freshness Checklist

- [ ] Verify command examples still run from the documented working directory.
- [ ] Verify all documented file paths still exist.
- [ ] Verify documented dependencies match currently used packages.
- [ ] Verify API route examples still match backend behavior.
- [ ] Verify cross-links between docs resolve correctly.

## Strategies Backlog
- [ ] Add first strategy hypothesis
- [ ] Define baseline benchmark
- [ ] Define success criteria for first test
- [ ] Expand topic proxy mappings beyond the initial sector ETF set.
- [ ] Evaluate paid or curated macro/news providers behind the Phase 3 feature-provider seam.
- [ ] Add regime-based strategy rotation policy layer (deferred by design).

## Tooling and Packages (Optional / Future Evaluation)

### Data Source Alternatives

- `yahooquery`
- `pandas-datareader`
- `alpha_vantage`
- `tiingo`
- `polygon-api-client`
- `ccxt` (crypto exchange data)

### Indicators and Technical Analysis

- `scikit-learn`
- `scipy`
- `pandas-ta`
- `ta`

### Visualization and Reporting

- `plotly`
- `mplfinance`

### Backtesting and Performance

Backtesting-specific tools and notes have been moved to:
- `docs/backtesting/README.md`

Additional candidates:
- `quantstats`
- `vectorbt`
- `backtrader`

### Additional Data and API Access

- `requests`
- `httpx`

### Deep Learning Candidates

- `torch`
- `pytorch-lightning`