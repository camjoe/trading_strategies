from pathlib import Path


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

    default_run_file = Path("run_tickers.txt")
    if default_run_file.exists():
        loaded = load_tickers_from_file(str(default_run_file))
        if loaded:
            return loaded

    return ["AAPL"]
