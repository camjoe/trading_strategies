from pathlib import Path
from common.tickers import load_tickers_from_file as _load_tickers_from_file
from common.tickers import parse_ticker_tokens as _parse_ticker_tokens
from common.tickers import load_ticker_categories as _load_ticker_categories


def parse_ticker_tokens(text: str) -> list[str]:
    return _parse_ticker_tokens(text)


def load_tickers_from_file(file_path: str) -> list[str]:
    return _load_tickers_from_file(file_path)


def load_ticker_categories(file_path: str) -> dict[str, list[str]]:
    return _load_ticker_categories(file_path)


def resolve_tickers(args: object) -> list[str]:
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

    if args.ticker:
        return [args.ticker.strip().upper()]

    default_run_file = Path("trends/assets/run_tickers.txt")
    if default_run_file.exists():
        loaded = load_tickers_from_file(str(default_run_file))
        if loaded:
            return loaded

    return ["AAPL"]
