import pandas as pd
import yfinance as yf


def print_column_debug(ticker: str, df: pd.DataFrame, stage: str) -> None:
    print(f"[{ticker}] {stage} column debug:")
    print(f"  column_index_type={type(df.columns).__name__}")
    print(f"  column_names={list(df.columns.names)}")
    if isinstance(df.columns, pd.MultiIndex):
        preview = [tuple(col) for col in list(df.columns)[:6]]
        print(f"  columns_preview={preview}")
    else:
        preview = [str(col) for col in list(df.columns)[:10]]
        print(f"  columns_preview={preview}")


def fetch_data(ticker: str, period: str, interval: str, debug_columns: bool = False) -> pd.DataFrame:
    df = yf.download(ticker, period=period, interval=interval, auto_adjust=True)
    if df.empty:
        raise ValueError(
            f"No data returned for ticker '{ticker}' (period={period}, interval={interval})."
        )

    if debug_columns:
        print_column_debug(ticker, df, "before-normalize")

    if isinstance(df.columns, pd.MultiIndex):
        if "Ticker" in df.columns.names:
            ticker_level = df.columns.names.index("Ticker")
            tickers = df.columns.get_level_values(ticker_level)
            if ticker in tickers:
                df = df.xs(ticker, axis=1, level="Ticker", drop_level=True)
            else:
                first_ticker = tickers[0]
                df = df.xs(first_ticker, axis=1, level="Ticker", drop_level=True)
        else:
            df.columns = df.columns.get_level_values(0)

    if debug_columns:
        print_column_debug(ticker, df, "after-normalize")

    return df
