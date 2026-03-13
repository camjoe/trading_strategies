import argparse

import pytest

from trends.tickers import load_ticker_categories, load_tickers_from_file, resolve_tickers


def test_load_tickers_from_file_dedupes_and_ignores_comments(tmp_path) -> None:
    ticker_file = tmp_path / "tickers.txt"
    ticker_file.write_text("# comment\nAAPL\nMSFT, AAPL\n\nNVDA\n", encoding="utf-8")

    tickers = load_tickers_from_file(str(ticker_file))

    assert tickers == ["AAPL", "MSFT", "NVDA"]


def test_load_ticker_categories_parses_sections(tmp_path) -> None:
    category_file = tmp_path / "cats.txt"
    category_file.write_text("[tech]\nAAPL, MSFT\nNVDA\n\n[etf]\nSPY, QQQ\n", encoding="utf-8")

    categories = load_ticker_categories(str(category_file))

    assert categories["tech"] == ["AAPL", "MSFT", "NVDA"]
    assert categories["etf"] == ["SPY", "QQQ"]


def test_resolve_tickers_prefers_explicit_ticker() -> None:
    args = argparse.Namespace(
        category=None,
        category_file="ticker_categories.txt",
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
