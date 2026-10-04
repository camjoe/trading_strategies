from __future__ import annotations

import json
from pathlib import Path

from scripts.checks.repo.sector_map_check import run_sector_map_check


def _build(root: Path, *, sector_map: dict[str, str] | None, universes: dict[str, str]) -> None:
    config = root / "src/infrastructure/config"
    (config / "trade_universes").mkdir(parents=True)
    if sector_map is not None:
        (config / "symbol_sectors.json").write_text(json.dumps(sector_map), encoding="utf-8")
    for name, body in universes.items():
        (config / "trade_universes" / name).write_text(body, encoding="utf-8")


class TestSectorMapCoverage:
    def test_passes_when_every_symbol_is_mapped(self, tmp_path: Path) -> None:
        _build(
            tmp_path,
            sector_map={"AAPL": "technology", "XOM": "energy"},
            universes={"default.txt": "AAPL\nXOM\n"},
        )
        assert run_sector_map_check(tmp_path) == 0

    def test_fails_on_a_symbol_missing_from_the_map(self, tmp_path: Path, capsys) -> None:
        _build(
            tmp_path,
            sector_map={"AAPL": "technology"},
            universes={"default.txt": "AAPL\nMSFT\n"},
        )
        assert run_sector_map_check(tmp_path) == 1
        assert "MSFT" in capsys.readouterr().out

    def test_ignores_comments_and_blank_lines(self, tmp_path: Path) -> None:
        _build(
            tmp_path,
            sector_map={"AAPL": "technology"},
            universes={"default.txt": "# a comment\n\n  AAPL  \n"},
        )
        assert run_sector_map_check(tmp_path) == 0

    def test_matches_symbols_case_insensitively(self, tmp_path: Path) -> None:
        _build(
            tmp_path,
            sector_map={"aapl": "technology"},
            universes={"default.txt": "AAPL\n"},
        )
        assert run_sector_map_check(tmp_path) == 0

    def test_fails_on_a_blank_sector_value(self, tmp_path: Path, capsys) -> None:
        _build(
            tmp_path,
            sector_map={"AAPL": "   "},
            universes={"default.txt": "AAPL\n"},
        )
        assert run_sector_map_check(tmp_path) == 1
        assert "blank sector" in capsys.readouterr().out

    def test_fails_when_the_sector_map_is_absent(self, tmp_path: Path) -> None:
        _build(tmp_path, sector_map=None, universes={"default.txt": "AAPL\n"})
        assert run_sector_map_check(tmp_path) == 1

    def test_fails_when_no_universe_files_exist(self, tmp_path: Path, capsys) -> None:
        _build(tmp_path, sector_map={"AAPL": "technology"}, universes={})
        assert run_sector_map_check(tmp_path) == 1
        assert "no trade universe files" in capsys.readouterr().out
