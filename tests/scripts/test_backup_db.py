from collections.abc import Iterator
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
