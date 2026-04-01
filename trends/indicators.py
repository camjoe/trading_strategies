import math

import pandas as pd


def print_indicator_explanations() -> None:
    print("Indicator explanations:")
    print("- RS (Relative Strength): average gain / average loss over the RSI window.")
    print("  RS > 1 means gains are stronger than losses in that window.")
    print("- RSI14: a 0-100 transform of RS used to spot momentum extremes.")
    print("- MACD: EMA(12) - EMA(26), comparing short-term and long-term momentum.")
    print("  Positive MACD suggests short-term trend is stronger than long-term trend.")
    print("- MACDSignal: 9-period EMA of MACD, used as a smoother trigger line.")
    print("  MACD crossing above/below MACDSignal is often used as a momentum signal.")


def calculate_rs_rsi(close: pd.Series, window: int = 14) -> tuple[pd.Series, pd.Series]:
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
    rsi = 100 - (100 / (1 + rs))
    # Clamp to [0, 100] to guard against any residual float edge cases.
    rsi = rsi.clip(lower=0.0, upper=100.0)
    return rs, rsi


def calculate_macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    # Coerce inf/-inf to NaN so EMA calculations stay bounded.
    close_clean = close.replace([math.inf, -math.inf], float("nan"))
    ema12 = close_clean.ewm(span=12, adjust=False).mean()
    ema26 = close_clean.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - macd_signal
    return macd, macd_signal, macd_hist


def calculate_bollinger_bands(
    close: pd.Series,
    window: int = 20,
    num_std: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    # Coerce inf/-inf to NaN so band calculations stay bounded.
    close_clean = close.replace([math.inf, -math.inf], float("nan"))
    middle = close_clean.rolling(window=window).mean()
    std = close_clean.rolling(window=window).std(ddof=0)
    upper = middle + (num_std * std)
    lower = middle - (num_std * std)
    return lower, middle, upper


def calculate_annualized_volatility_pct(close: pd.Series, window: int = 20) -> pd.Series:
    # Coerce inf/-inf to NaN so return calculations stay bounded.
    close_clean = close.replace([math.inf, -math.inf], float("nan"))
    returns = close_clean.pct_change()
    return returns.rolling(window=window).std(ddof=0) * (252 ** 0.5) * 100.0


def add_trend_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    # Coerce inf/-inf in Close to NaN so all downstream indicators stay bounded.
    out["Close"] = out["Close"].replace([math.inf, -math.inf], float("nan"))
    out["MA20"] = out["Close"].rolling(window=20).mean()
    out["MA50"] = out["Close"].rolling(window=50).mean()
    out["MA200"] = out["Close"].rolling(window=200).mean()

    out["RS"], out["RSI14"] = calculate_rs_rsi(out["Close"], window=14)
    out["MACD"], out["MACDSignal"], out["MACDHist"] = calculate_macd(out["Close"])

    out["DailyReturnPct"] = out["Close"].pct_change() * 100
    return out
