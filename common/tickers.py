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
