"""Financial and technical indicator constants shared across modules."""

# ---------------------------------------------------------------------------
# Settlement
# ---------------------------------------------------------------------------

# Ticker symbol used to represent cash in the ledger; buy trades on this ticker
# are treated as cash inflows (no equity position is created).
SETTLEMENT_TICKER = "CASH"

# ---------------------------------------------------------------------------
# Time and annualization
# ---------------------------------------------------------------------------

# Number of trading days in a year; used as the annualization factor
# when converting daily volatility/returns to annualized figures.
TRADING_DAYS_PER_YEAR = 252

# Number of seconds in one calendar day
SECONDS_PER_DAY = 86_400

# Divisor for converting basis points to a decimal fraction (1 bps = 0.0001)
BASIS_POINTS_DIVISOR = 10_000

# ---------------------------------------------------------------------------
# RSI indicator
# ---------------------------------------------------------------------------

# RSI oscillates on a 0–100 scale; used in the core RSI formula
RSI_SCALE = 100

# Standard RSI lookback period (J. Welles Wilder's original 14-day default)
RSI_DEFAULT_WINDOW = 14

# Conventional oversold threshold — readings below this suggest buying pressure
RSI_OVERSOLD = 30

# Conventional overbought threshold — readings above this suggest selling pressure
RSI_OVERBOUGHT = 70

# ---------------------------------------------------------------------------
# MACD indicator (EMA spans)
# ---------------------------------------------------------------------------

# Fast EMA period used for the MACD line (EMA12 − EMA26)
MACD_FAST_SPAN = 12

# Slow EMA period used for the MACD line
MACD_SLOW_SPAN = 26

# EMA period for the MACD signal (trigger) line
MACD_SIGNAL_SPAN = 9

# Minimum history bars needed before the MACD signal line has enough data
# to generate a reliable crossover: slow span + signal span warm-up.
MACD_MIN_HISTORY = MACD_SLOW_SPAN + MACD_SIGNAL_SPAN
