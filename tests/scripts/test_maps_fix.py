from __future__ import annotations

from pathlib import Path

from scripts.fixes.maps_fix import fix_map, run_maps_fix


def _write(path: Path, content: str = "x = 1\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_fix_map_removes_stale_only_rows(tmp_path: Path) -> None:
    _write(tmp_path / "src/trading/domain/accounting.py")
    _write(
        tmp_path / "map.md",
        "### `src/trading/domain/`\n"
        "| Module | Responsibility |\n"
        "| `accounting.py` | domain accounting |\n"
        "| `ghost.py` | deleted module |\n",
    )

    report = fix_map(tmp_path, "map.md", "src/trading")

    assert report.removed == ["| `ghost.py` | deleted module |"]
    assert report.mixed == []
    content = (tmp_path / "map.md").read_text(encoding="utf-8")
    assert "ghost.py" not in content
    assert "| `accounting.py` | domain accounting |" in content
    assert content.endswith("\n")


def test_fix_map_keeps_and_reports_mixed_rows(tmp_path: Path) -> None:
    _write(tmp_path / "src/trading/domain/accounting.py")
    _write(
        tmp_path / "map.md",
        "### `src/trading/domain/`\n| `accounting.py`, `ghost.py` | pair row |\n",
    )

    report = fix_map(tmp_path, "map.md", "src/trading")

    assert report.removed == []
    assert report.mixed == ["| `accounting.py`, `ghost.py` | pair row |"]
    assert "ghost.py" in (tmp_path / "map.md").read_text(encoding="utf-8")


def test_fix_map_is_noop_when_in_sync(tmp_path: Path) -> None:
    _write(tmp_path / "src/trading/domain/accounting.py")
    original = "### `src/trading/domain/`\n| `accounting.py` | domain accounting |\n"
    _write(tmp_path / "map.md", original)

    report = fix_map(tmp_path, "map.md", "src/trading")

    assert report.removed == []
    assert report.mixed == []
    assert (tmp_path / "map.md").read_text(encoding="utf-8") == original


def test_run_maps_fix_processes_present_maps_only(tmp_path: Path) -> None:
    _write(tmp_path / "src/trading/services/accounts/queries.py")
    _write(
        tmp_path / "docs/maps/trading-package-map.md",
        "### `src/trading/services/`\n| `accounts/queries.py` | account reads |\n| `accounts/ghost.py` | deleted |\n",
    )

    assert run_maps_fix(repo_root=tmp_path) == 0

    content = (tmp_path / "docs/maps/trading-package-map.md").read_text(encoding="utf-8")
    assert "ghost.py" not in content
    assert "accounts/queries.py" in content
