# Backtesting Tooling

Backtesting in this repository runs on the in-house engine under:
- `trading/backtesting/`

Optional external packages that may be evaluated later are tracked in:
- `docs/Tooling and Packages.md`

Operational notes:
- Keep assumptions explicit (slippage, fees, execution timing).
- Prefer chronological validation with rolling or walk-forward windows.
- Compare against simple baselines and benchmark returns.
