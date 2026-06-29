from __future__ import annotations

from pathlib import Path

import pytest

from common.tickers import (
    load_ticker_categories,
    load_tickers_from_file,
    parse_ticker_tokens,
)


class TestParseTickerTokens:
    def test_normalizes_case_and_splits_commas_and_whitespace(self) -> None:
        tokens = parse_ticker_tokens(" aapl, msft   goog\nTSLA ")
        assert tokens == ["AAPL", "MSFT", "GOOG", "TSLA"]

    def test_ignores_empty_tokens(self) -> None:
        tokens = parse_ticker_tokens(" , ,   ")
        assert tokens == []


class TestLoadTickersFromFile:
    def test_raises_when_file_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.txt"
        with pytest.raises(FileNotFoundError, match="Ticker file not found"):
            load_tickers_from_file(str(missing))

    def test_loads_deduplicated_tickers_skipping_comments_and_blank_lines(self, tmp_path: Path) -> None:
        tickers_file = tmp_path / "tickers.txt"
        tickers_file.write_text(
            "\n".join(
                [
                    "# Comment line",
                    "AAPL, msft",
                    "",
                    "  GOOG   tsla",
                    "MSFT",
                    "# trailing comment",
                ]
            ),
            encoding="utf-8",
        )

        loaded = load_tickers_from_file(str(tickers_file))
        assert loaded == ["AAPL", "MSFT", "GOOG", "TSLA"]


class TestLoadTickerCategories:
    def test_raises_when_file_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "categories.txt"
        with pytest.raises(FileNotFoundError, match="Category file not found"):
            load_ticker_categories(str(missing))

    def test_raises_when_ticker_lines_appear_before_category_header(self, tmp_path: Path) -> None:
        categories_file = tmp_path / "categories.txt"
        categories_file.write_text("AAPL\n[core]\nMSFT\n", encoding="utf-8")

        with pytest.raises(ValueError, match=r"ticker entries must be inside \[category\] sections"):
            load_ticker_categories(str(categories_file))

    def test_loads_categories_normalizes_names_and_deduplicates_tickers(self, tmp_path: Path) -> None:
        categories_file = tmp_path / "categories.txt"
        categories_file.write_text(
            "\n".join(
                [
                    "# strategy buckets",
                    "[ Core ]",
                    "AAPL msft",
                    "AAPL",
                    "",
                    "[satellite]",
                    "tsla, nvda",
                    "[core]",
                    "GOOG",
                ]
            ),
            encoding="utf-8",
        )

        loaded = load_ticker_categories(str(categories_file))
        assert loaded == {
            "core": ["AAPL", "MSFT", "GOOG"],
            "satellite": ["TSLA", "NVDA"],
        }
