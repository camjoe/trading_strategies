# Tooling and Packages

Reference list of useful Python packages, data providers, and VS Code extensions for trading research workflows.

## Data Source Alternatives to yfinance

- `yahooquery`
- `pandas-datareader`
- `alpha_vantage`
- `tiingo`
- `polygon-api-client`
- `ccxt` (crypto exchange data)

## Python Packages Often Used

### Core Analysis
- `pandas`
- `numpy`
- `scipy`
- `statsmodels`
- `scikit-learn`

### Charting and Visualization
- `matplotlib`
- `plotly`
- `mplfinance`

### Indicators and Technical Analysis
- `pandas-ta`
- `ta`

### Backtesting and Performance

Backtesting-specific tools and notes have been moved to:
- `docs/backtesting/Tooling.md`

### Data and API Access
- `yfinance`
- `requests`
- `httpx`

### Optional for Deep Learning Workflows
- `torch`
- `pytorch-lightning`

## VS Code Extensions

- `ms-python.python`
- `ms-python.vscode-pylance`
- `ms-toolsai.jupyter`
- `charliermarsh.ruff`
- `ms-python.black-formatter`
- `eamodio.gitlens`

## Example Install Commands

Install a basic research stack:

```powershell
pip install pandas numpy scipy scikit-learn statsmodels matplotlib yfinance
```

Install optional strategy/analysis tools:

```powershell
pip install pandas-ta quantstats vectorbt backtrader plotly
```

Install crypto-focused data access:

```powershell
pip install ccxt
```

## Notes

- Keep production-sensitive workflows on more reliable paid feeds when needed.
- Free data is useful for prototyping but can have gaps, revisions, or rate limits.
- Pin versions in `requirements.txt` for reproducibility.
