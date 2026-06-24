import argparse

from apps.trends.tickers import resolve_tickers


def test_resolve_tickers_prefers_explicit_ticker() -> None:
    args = argparse.Namespace(
        category=None,
        category_file="apps/trends/assets/ticker_categories.txt",
        tickers_file=None,
        ticker="nvda",
    )

    tickers = resolve_tickers(args)

    assert tickers == ["NVDA"]


def test_resolve_tickers_from_category(tmp_path) -> None:
    category_file = tmp_path / "cats.txt"
    category_file.write_text("[energy]\nXOM, CVX\n", encoding="utf-8")

    args = argparse.Namespace(
        category="energy",
        category_file=str(category_file),
        tickers_file=None,
        ticker=None,
    )

    tickers = resolve_tickers(args)

    assert tickers == ["XOM", "CVX"]
