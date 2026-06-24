from pathlib import Path

from common.tickers import load_ticker_categories, load_tickers_from_file


def resolve_tickers(args: object) -> list[str]:
    if args.category:
        categories = load_ticker_categories(args.category_file)
        key = args.category.strip().lower()
        if key not in categories:
            available = ", ".join(sorted(categories.keys()))
            raise ValueError(f"Unknown category '{args.category}'. Available categories: {available}")
        return categories[key]

    if args.tickers_file:
        return load_tickers_from_file(args.tickers_file)

    if args.ticker:
        return [args.ticker.strip().upper()]

    default_run_file = Path("apps/trends/assets/run_tickers.txt")
    if default_run_file.exists():
        loaded = load_tickers_from_file(str(default_run_file))
        if loaded:
            return loaded

    return ["AAPL"]
