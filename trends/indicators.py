import math

import pandas as pd

from common.constants import (
    MACD_FAST_SPAN,
    MACD_SIGNAL_SPAN,
    MACD_SLOW_SPAN,
    RSI_DEFAULT_WINDOW,
    RSI_SCALE,
    TRADING_DAYS_PER_YEAR,
)

# ---------------------------------------------------------------------------
# Moving average window periods (also used as DataFrame column label suffixes)
# ---------------------------------------------------------------------------
MA_SHORT_WINDOW = 20    # Short-term SMA; also the default Bollinger / vol window
MA_MEDIUM_WINDOW = 50   # Medium-term SMA
MA_LONG_WINDOW = 200    # Long-term SMA

# Default window for annualized volatility rolling calculation
ANNUALIZED_VOL_DEFAULT_WINDOW = 20

# Default Bollinger Band parameters
BOLLINGER_DEFAULT_WINDOW = 20
BOLLINGER_DEFAULT_NUM_STD = 2.0


def print_indicator_explanations() -> None:
    print("Indicator explanations:")
    print("- RS (Relative Strength): average gain / average loss over the RSI window.")
    print("  RS > 1 means gains are stronger than losses in that window.")
    print("- RSI14: a 0-100 transform of RS used to spot momentum extremes.")
    print("- MACD: EMA(12) - EMA(26), comparing short-term and long-term momentum.")
    print("  Positive MACD suggests short-term trend is stronger than long-term trend.")
    print("- MACDSignal: 9-period EMA of MACD, used as a smoother trigger line.")
    print("  MACD crossing above/below MACDSignal is often used as a momentum signal.")


def calculate_rs_rsi(close: pd.Series, window: int = RSI_DEFAULT_WINDOW) -> tuple[pd.Series, pd.Series]:
    # Coerce inf/-inf to NaN so rolling math stays bounded.
    close_clean = close.replace([math.inf, -math.inf], float("nan"))
    delta = close_clean.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    rs = avg_gain / avg_loss
    # Flat rolling windows (avg_gain == avg_loss == 0) produce 0/0 = NaN.
    # Treat as neutral momentum (RS = 1 → RSI = 50) rather than propagating NaN.
    flat_mask = (avg_gain == 0) & (avg_loss == 0)
    rs = rs.where(~flat_mask, other=1.0)
    rsi = RSI_SCALE - (RSI_SCALE / (1 + rs))
    # Clamp to [0, 100] to guard against any residual float edge cases.
    rsi = rsi.clip(lower=0.0, upper=float(RSI_SCALE))
    return rs, rsi


def calculate_macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    # Coerce inf/-inf to NaN so EMA calculations stay bounded.
    close_clean = close.replace([math.inf, -math.inf], float("nan"))
    ema12 = close_clean.ewm(span=MACD_FAST_SPAN, adjust=False).mean()
    ema26 = close_clean.ewm(span=MACD_SLOW_SPAN, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=MACD_SIGNAL_SPAN, adjust=False).mean()
    macd_hist = macd - macd_signal
    return macd, macd_signal, macd_hist


def calculate_bollinger_bands(
    close: pd.Series,
    window: int = BOLLINGER_DEFAULT_WINDOW,
    num_std: float = BOLLINGER_DEFAULT_NUM_STD,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    # Coerce inf/-inf to NaN so band calculations stay bounded.
    close_clean = close.replace([math.inf, -math.inf], float("nan"))
    middle = close_clean.rolling(window=window).mean()
    std = close_clean.rolling(window=window).std(ddof=0)
    upper = middle + (num_std * std)
    lower = middle - (num_std * std)
    return lower, middle, upper


def calculate_annualized_volatility_pct(close: pd.Series, window: int = ANNUALIZED_VOL_DEFAULT_WINDOW) -> pd.Series:
    # Coerce inf/-inf to NaN so return calculations stay bounded.
    close_clean = close.replace([math.inf, -math.inf], float("nan"))
    returns = close_clean.pct_change()
    return returns.rolling(window=window).std(ddof=0) * (TRADING_DAYS_PER_YEAR ** 0.5) * 100.0


def add_trend_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    # Coerce inf/-inf in Close to NaN so all downstream indicators stay bounded.
    out["Close"] = out["Close"].replace([math.inf, -math.inf], float("nan"))
    out["MA20"] = out["Close"].rolling(window=MA_SHORT_WINDOW).mean()
    out["MA50"] = out["Close"].rolling(window=MA_MEDIUM_WINDOW).mean()
    out["MA200"] = out["Close"].rolling(window=MA_LONG_WINDOW).mean()

    out["RS"], out["RSI14"] = calculate_rs_rsi(out["Close"], window=RSI_DEFAULT_WINDOW)
    out["MACD"], out["MACDSignal"], out["MACDHist"] = calculate_macd(out["Close"])

    out["DailyReturnPct"] = out["Close"].pct_change() * 100
    return out
