from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading.services.books.sector_config import load_symbol_sector_map


def test_load_symbol_sector_map_missing_file_returns_empty_map(tmp_path: Path) -> None:
    assert load_symbol_sector_map(tmp_path / "missing.json") == {}


def test_load_symbol_sector_map_normalizes_symbols_and_sectors(tmp_path: Path) -> None:
    path = tmp_path / "symbol_sectors.json"
    path.write_text(
        json.dumps(
            {
                " aapl ": " Technology ",
                "MSFT": "technology",
                "EMPTY_SYMBOL": "   ",
                "   ": "financials",
            }
        ),
        encoding="utf-8",
    )

    assert load_symbol_sector_map(path) == {
        "AAPL": "technology",
        "MSFT": "technology",
    }


def test_load_symbol_sector_map_rejects_non_object_root(tmp_path: Path) -> None:
    path = tmp_path / "symbol_sectors.json"
    path.write_text(json.dumps(["AAPL", "MSFT"]), encoding="utf-8")

    with pytest.raises(ValueError, match="JSON object"):
        load_symbol_sector_map(path)


def test_load_symbol_sector_map_rejects_non_string_entries(tmp_path: Path) -> None:
    path = tmp_path / "symbol_sectors.json"
    path.write_text(json.dumps({"AAPL": 1}), encoding="utf-8")

    with pytest.raises(ValueError, match="string symbol"):
        load_symbol_sector_map(path)
