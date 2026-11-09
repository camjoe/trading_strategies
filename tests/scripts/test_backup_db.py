from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from infrastructure.database.backend import SQLiteBackend, use_backend
from scripts.data_ops import backup_db
from tests.support.db_schema import build_db_at_head


@pytest.fixture
def live_db(tmp_path: Path) -> Iterator[Path]:
    db_path = build_db_at_head(tmp_path / "paper_trading.db")
    with use_backend(SQLiteBackend(db_path)):
        yield db_path


def test_run_backup_writes_into_the_shared_data_folder(
    live_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRADING_DATA_HOME", str(tmp_path / "shared"))

    summary = backup_db.run_backup(verbose=False)

    backup = Path(str(summary["backup"]))
    assert backup.parent == (tmp_path / "shared" / "db_backups").resolve()
    assert backup.exists()


def test_run_backup_prefers_the_backup_folder_setting(
    live_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRADING_DATA_HOME", str(tmp_path / "shared"))
    monkeypatch.setenv("TRADING_DB_BACKUPS_DIR", str(tmp_path / "backups"))

    summary = backup_db.run_backup(verbose=False)

    assert Path(str(summary["backup"])).parent == (tmp_path / "backups").resolve()


def test_a_suffixed_backup_name_still_carries_its_stamp() -> None:
    assert backup_db._parse_stamp(Path("paper_trading_20260327_080910_2.db")) == datetime(2026, 3, 27, 8, 9, 10)
    assert backup_db._parse_stamp(Path("paper_trading_20260327_080910.db")) == datetime(2026, 3, 27, 8, 9, 10)
    assert backup_db._parse_stamp(Path("paper_trading_notastamp.db")) is None


def test_retention_counts_every_checkouts_backups_in_a_shared_folder(
    live_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared = tmp_path / "shared" / "db_backups"
    shared.mkdir(parents=True)
    other_checkout = [
        shared / f"paper_trading_20260301_{second:06d}.db" for second in range(backup_db.KEEP_RECENT + 5)
    ]
    for path in other_checkout:
        path.write_bytes(b"x")
    monkeypatch.setenv("TRADING_DATA_HOME", str(tmp_path / "shared"))

    summary = backup_db.run_backup(verbose=False)

    pruned_paths = summary["pruned"]
    assert isinstance(pruned_paths, list)
    pruned = {path.name for path in pruned_paths}
    survivors = {path.name for path in shared.glob("paper_trading_*.db")}
    assert len(survivors) == backup_db.KEEP_RECENT + 1
    assert other_checkout[0].name in survivors
    assert pruned == {path.name for path in other_checkout[1:6]}
    assert Path(str(summary["backup"])).name in survivors
