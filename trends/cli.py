import argparse


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
