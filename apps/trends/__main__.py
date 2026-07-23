from __future__ import annotations

from apps.trends.charts import plot_trends
from apps.trends.cli import parse_args
from apps.trends.data import fetch_data
from apps.trends.indicators import add_trend_features, print_indicator_explanations
from apps.trends.tickers import resolve_tickers
from common.tickers import load_ticker_categories
from infrastructure.market_data.factory import build_provider


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

    provider = build_provider()
    for ticker in tickers:
        try:
            data = fetch_data(ticker, args.period, args.interval, provider=provider, debug_columns=args.debug_columns)
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
