import argparse
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot stock trends using yfinance and matplotlib."
    )
    parser.add_argument("ticker", nargs="?", default=None, help="Single ticker symbol, e.g. AAPL")
    parser.add_argument("--period", default="1y", help="Data period, e.g. 6mo, 1y, 5y")
    parser.add_argument("--interval", default="1d", help="Data interval, e.g. 1d, 1wk, 1h")
    parser.add_argument(
        "--tickers-file",
        default=None,
        help="Path to a text file of tickers for this run (one per line or comma-separated).",
    )
    parser.add_argument(
        "--category",
        default=None,
        help="Category name from the category file, e.g. tech or indices.",
    )
    parser.add_argument(
        "--category-file",
        default="ticker_categories.txt",
        help="Path to category file with [category] sections.",
    )
    parser.add_argument(
        "--list-categories",
        action="store_true",
        help="Print categories from --category-file and exit.",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Print plain-English definitions for RS/RSI, MACD, and MACDSignal.",
    )
    parser.add_argument(
        "--debug-columns",
        action="store_true",
        help="Print dataframe column structure before/after normalization.",
    )
    return parser.parse_args()


def parse_ticker_tokens(text: str) -> list[str]:
    tokens = text.replace(",", " ").split()
    return [t.strip().upper() for t in tokens if t.strip()]


def load_tickers_from_file(file_path: str) -> list[str]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Ticker file not found: {file_path}")

    tickers: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tickers.extend(parse_ticker_tokens(line))

    # Keep order but drop duplicates.
    return list(dict.fromkeys(tickers))


def load_ticker_categories(file_path: str) -> dict[str, list[str]]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Category file not found: {file_path}")

    categories: dict[str, list[str]] = {}
    current_category: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            current_category = line[1:-1].strip().lower()
            categories.setdefault(current_category, [])
            continue

        if current_category is None:
            raise ValueError(
                "Invalid category file format: ticker entries must be inside [category] sections."
            )

        categories[current_category].extend(parse_ticker_tokens(line))

    for category, tickers in categories.items():
        categories[category] = list(dict.fromkeys(tickers))

    return categories


def resolve_tickers(args: argparse.Namespace) -> list[str]:
    if args.category:
        categories = load_ticker_categories(args.category_file)
        key = args.category.strip().lower()
        if key not in categories:
            available = ", ".join(sorted(categories.keys()))
            raise ValueError(
                f"Unknown category '{args.category}'. Available categories: {available}"
            )
        return categories[key]

    if args.tickers_file:
        return load_tickers_from_file(args.tickers_file)

    # Explicit CLI ticker should override default file-based selection.
    if args.ticker:
        return [args.ticker.strip().upper()]

    default_run_file = Path("run_tickers.txt")
    if default_run_file.exists():
        loaded = load_tickers_from_file(str(default_run_file))
        if loaded:
            return loaded

    return ["AAPL"]


def print_indicator_explanations() -> None:
    print("Indicator explanations:")
    print("- RS (Relative Strength): average gain / average loss over the RSI window.")
    print("  RS > 1 means gains are stronger than losses in that window.")
    print("- RSI14: a 0-100 transform of RS used to spot momentum extremes.")
    print("- MACD: EMA(12) - EMA(26), comparing short-term and long-term momentum.")
    print("  Positive MACD suggests short-term trend is stronger than long-term trend.")
    print("- MACDSignal: 9-period EMA of MACD, used as a smoother trigger line.")
    print("  MACD crossing above/below MACDSignal is often used as a momentum signal.")


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
        # Newer yfinance versions may return MultiIndex columns even for one ticker.
        # Flatten to standard OHLCV columns so downstream math gets 1D Series.
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


def calculate_rs_rsi(close: pd.Series, window: int = 14) -> tuple[pd.Series, pd.Series]:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()

    # RS (Relative Strength) = average gain / average loss over the RSI window.
    # Plain meaning: if RS > 1, recent gains are larger than recent losses.
    rs = avg_gain / avg_loss

    # RSI transforms RS to a bounded 0-100 oscillator for easier interpretation.
    rsi = 100 - (100 / (1 + rs))
    return rs, rsi


def calculate_macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()

    # MACD = EMA(12) - EMA(26).
    # Plain meaning: positive MACD suggests short-term momentum is above long-term trend.
    macd = ema12 - ema26

    # MACDSignal = 9-period EMA of MACD.
    # Plain meaning: a smoothed trigger line used for crossover signals with MACD.
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


def build_chart_path(ticker: str, period: str, interval: str) -> Path:
    charts_dir = Path("charts")
    charts_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ticker.upper()}_{period}_{interval}_{ts}.png".replace("/", "-")
    return charts_dir / filename


def plot_trends(
    df: pd.DataFrame,
    ticker: str,
    period: str,
    interval: str,
    show_chart: bool,
) -> Path:
    fig, axes = plt.subplots(
        nrows=3,
        ncols=1,
        figsize=(12, 10),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1, 2]},
    )

    ax_price, ax_volume, ax_indicators = axes

    ax_price.plot(df.index, df["Close"], label="Close", linewidth=1.4)
    ax_price.plot(df.index, df["MA20"], label="MA20", linewidth=1.0)
    ax_price.plot(df.index, df["MA50"], label="MA50", linewidth=1.0)
    ax_price.plot(df.index, df["MA200"], label="MA200", linewidth=1.0)
    ax_price.set_title(f"{ticker.upper()} Price Trend ({period}, {interval})")
    ax_price.set_ylabel("Price")
    ax_price.grid(alpha=0.25)
    ax_price.legend(loc="best")

    ax_volume.bar(df.index, df["Volume"], width=1.0, alpha=0.6, label="Volume")
    ax_volume.set_ylabel("Volume")
    ax_volume.grid(alpha=0.2)

    ax_indicators.plot(df.index, df["RSI14"], label="RSI14", linewidth=1.0)
    ax_indicators.axhline(70, color="red", linestyle="--", linewidth=0.8, alpha=0.8)
    ax_indicators.axhline(30, color="green", linestyle="--", linewidth=0.8, alpha=0.8)
    ax_indicators.set_ylabel("RSI")
    ax_indicators.set_ylim(0, 100)
    ax_indicators.grid(alpha=0.2)

    ax_macd = ax_indicators.twinx()
    colors = ["#2ca02c" if h >= 0 else "#d62728" for h in df["MACDHist"]]
    ax_macd.bar(df.index, df["MACDHist"], color=colors, alpha=0.25, label="MACD Hist")
    ax_macd.plot(df.index, df["MACD"], label="MACD", linewidth=1.0)
    ax_macd.plot(df.index, df["MACDSignal"], label="Signal", linewidth=1.0)
    ax_macd.set_ylabel("MACD")

    lines1, labels1 = ax_indicators.get_legend_handles_labels()
    lines2, labels2 = ax_macd.get_legend_handles_labels()
    ax_indicators.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    ax_indicators.set_xlabel("Date")

    latest = df.iloc[-1]
    latest_return = latest["DailyReturnPct"]
    fig.suptitle(
        f"Latest Close: {latest['Close']:.2f} | Daily Return: {latest_return:.2f}%",
        fontsize=10,
        y=0.98,
    )

    plt.tight_layout()
    chart_path = build_chart_path(ticker, period, interval)
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    if show_chart:
        plt.show()
    else:
        plt.close(fig)
    return chart_path


def main() -> None:
    args = parse_args()
    if args.explain:
        print_indicator_explanations()
        print()

    if args.list_categories:
        categories = load_ticker_categories(args.category_file)
        if not categories:
            print(f"No categories found in {args.category_file}")
            return

        print(f"Categories in {args.category_file}:")
        for name in sorted(categories.keys()):
            print(f"- {name} ({len(categories[name])} tickers)")
        return

    tickers = resolve_tickers(args)
    if not tickers:
        raise ValueError("No tickers selected. Add tickers to file or pass a ticker/category.")

    show_chart = len(tickers) == 1
    print(f"Selected tickers: {', '.join(tickers)}")
    if not show_chart:
        print("Batch mode: charts will be saved to disk without opening windows.")

    for ticker in tickers:
        try:
            data = fetch_data(ticker, args.period, args.interval, debug_columns=args.debug_columns)
            data = add_trend_features(data)

            print(f"\nTicker: {ticker}")
            print(
                data[
                    [
                        "Close",
                        "MA20",
                        "MA50",
                        "MA200",
                        "RSI14",
                        "RS",
                        "MACD",
                        "MACDSignal",
                        "DailyReturnPct",
                    ]
                ].tail(5)
            )
            saved_path = plot_trends(data, ticker, args.period, args.interval, show_chart)
            print(f"Saved chart: {saved_path}")
        except Exception as exc:
            print(f"Failed for {ticker}: {exc}")


if __name__ == "__main__":
    main()
