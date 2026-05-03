from argparse import Namespace
from datetime import datetime
from pathlib import Path

import pytest

from trading.database.db_backend import SQLiteBackend, get_backend, set_backend
from trading.database.db_init import ensure_db
from trading.interfaces.runtime.data_ops import admin
from tests.support.admin import seed_admin_dataset


class FixedDateTime:
    @classmethod
    def now(cls) -> datetime:
        return datetime(2026, 3, 27, 8, 9, 10)


@pytest.fixture
def configured_backend(tmp_path: Path):
    original = get_backend()
    backend = SQLiteBackend(tmp_path / "paper_trading.db")
    set_backend(backend)
    try:
        yield backend
    finally:
        set_backend(original)

class TestParseAccountNames:
    def test_parse_account_names_splits_deduplicates_and_strips(self) -> None:
        names = admin._parse_account_names(["acct_a, acct_b", "acct_b", " acct_c ", ""])

        assert names == ["acct_a", "acct_b", "acct_c"]


class TestBackupDatabase:
    def test_backup_database_raises_when_source_missing(self, configured_backend: SQLiteBackend) -> None:
        with pytest.raises(FileNotFoundError, match="Database file not found"):
            admin.backup_database()

    def test_backup_database_writes_timestamped_file_in_default_dir(
        self, configured_backend: SQLiteBackend, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ensure_db().close()
        monkeypatch.setattr(admin, "datetime", FixedDateTime)

        backup = admin.backup_database()

        assert backup.exists()
        assert backup.name.startswith("paper_trading_20260327_080910")
        assert backup.parent.name == "db_backups"

    def test_backup_database_accepts_explicit_file_destination(
        self, configured_backend: SQLiteBackend, tmp_path: Path
    ) -> None:
        ensure_db().close()
        destination = tmp_path / "custom" / "manual_backup.db"

        backup = admin.backup_database(str(destination))

        assert backup == destination
        assert backup.exists()

class TestCommandValidation:
    def test_cmd_delete_accounts_requires_yes_with_all(self) -> None:
        args = Namespace(
            accounts=[],
            all=True,
            yes=False,
            backup_before=False,
            backup_destination=None,
            dry_run=True,
        )

        with pytest.raises(ValueError, match="--all requires --yes"):
            admin._cmd_delete_accounts(args)

    def test_cmd_delete_accounts_requires_names_when_not_all(self) -> None:
        args = Namespace(
            accounts=[],
            all=False,
            yes=False,
            backup_before=False,
            backup_destination=None,
            dry_run=True,
        )

        with pytest.raises(ValueError, match="Provide at least one account name"):
            admin._cmd_delete_accounts(args)
