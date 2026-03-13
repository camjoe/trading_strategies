try:
    from trends.charts import plot_trends
    from trends.cli import parse_args
    from trends.data import fetch_data
    from trends.indicators import add_trend_features, print_indicator_explanations
    from trends.tickers import load_ticker_categories, resolve_tickers
except ModuleNotFoundError:
    from charts import plot_trends
    from cli import parse_args
    from data import fetch_data
    from indicators import add_trend_features, print_indicator_explanations
    from tickers import load_ticker_categories, resolve_tickers


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
