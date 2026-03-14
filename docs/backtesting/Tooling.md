# Backtesting Tooling

Backtesting and performance-focused packages commonly used for Python workflows:

- `quantstats`
- `vectorbt`
- `backtrader`

Install examples:

```powershell
pip install quantstats vectorbt backtrader
```

Notes:

- Keep assumptions explicit (slippage, fees, execution timing).
- Prefer chronological validation with rolling or walk-forward windows.
- Compare against simple baselines and benchmark returns.
