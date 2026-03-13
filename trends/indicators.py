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
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rs, rsi


def calculate_macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - macd_signal
    return macd, macd_signal, macd_hist


def add_trend_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["MA20"] = out["Close"].rolling(window=20).mean()
    out["MA50"] = out["Close"].rolling(window=50).mean()
    out["MA200"] = out["Close"].rolling(window=200).mean()

    out["RS"], out["RSI14"] = calculate_rs_rsi(out["Close"], window=14)
    out["MACD"], out["MACDSignal"], out["MACDHist"] = calculate_macd(out["Close"])

    out["DailyReturnPct"] = out["Close"].pct_change() * 100
    return out
