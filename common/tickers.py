from pathlib import Path


def parse_ticker_tokens(text: str) -> list[str]:
    tokens = text.replace(",", " ").split()
    return [t.strip().upper() for t in tokens if t.strip()]


def _iter_ticker_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def load_tickers_from_file(file_path: str) -> list[str]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Ticker file not found: {file_path}")

    tickers: list[str] = []
    for line in _iter_ticker_lines(path):
        tickers.extend(parse_ticker_tokens(line))

    return list(dict.fromkeys(tickers))


def load_ticker_categories(file_path: str) -> dict[str, list[str]]:
    """Load ticker categories from a file with [category] sections.

    File format:
        [category_name]
        AAPL MSFT GOOG
        TSLA

        [other_category]
        SPY VTI
    """
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
