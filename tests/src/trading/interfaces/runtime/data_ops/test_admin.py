from argparse import Namespace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import infrastructure.database.connection as db_init
from infrastructure.database.backend import SQLiteBackend, get_backend, set_backend
from tests.support.db_schema import build_db_at_head
from trading.interfaces.runtime.data_ops import admin


class FixedDateTime:
    @classmethod
    def now(cls) -> datetime:
        return datetime(2026, 3, 27, 8, 9, 10)


class FakeParser:
    def __init__(self, args: Namespace):
        self._args = args
        self.error_message: str | None = None

    def parse_args(self) -> Namespace:
        return self._args

    def error(self, message: str) -> None:
        self.error_message = message


@pytest.fixture
def configured_backend(tmp_path: Path):
    original = get_backend()
    backend = SQLiteBackend(tmp_path / "paper_trading.db")
    set_backend(backend)
    try:
        yield backend
    finally:
        set_backend(original)


class TestSqliteDbPath:
    def test_sqlite_db_path_rejects_non_sqlite_backends(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(admin, "get_backend", lambda: object())

        with pytest.raises(RuntimeError, match="supports only SQLite"):
            admin._sqlite_db_path()


class TestBackupDatabase:
    def test_backup_database_raises_when_source_missing(self, configured_backend: SQLiteBackend) -> None:
        with pytest.raises(FileNotFoundError, match="Database file not found"):
            admin.backup_database()

    def test_backup_database_writes_timestamped_file_in_default_dir(
        self,
        configured_backend: SQLiteBackend,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        build_db_at_head(configured_backend.db_path)
        monkeypatch.setattr(admin, "datetime", FixedDateTime)
        monkeypatch.setattr(admin, "DB_BACKUPS_DIR", tmp_path / "db_backups")

        backup = admin.backup_database()

        assert backup.exists()
        assert backup.name.startswith("paper_trading_20260327_080910")
        assert backup.parent == tmp_path / "db_backups"

    def test_backup_database_accepts_explicit_file_destination(
        self, configured_backend: SQLiteBackend, tmp_path: Path
    ) -> None:
        build_db_at_head(configured_backend.db_path)
        destination = tmp_path / "custom" / "manual_backup.db"

        backup = admin.backup_database(str(destination))

        assert backup == destination
        assert backup.exists()

    def test_backup_database_accepts_directory_destination(
        self,
        configured_backend: SQLiteBackend,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        build_db_at_head(configured_backend.db_path)
        monkeypatch.setattr(admin, "datetime", FixedDateTime)

        backup = admin.backup_database(str(tmp_path / "manual_backups"))

        assert backup.parent == tmp_path / "manual_backups"
        assert backup.name == "paper_trading_20260327_080910.db"
        assert backup.exists()


class TestHelpersAndCommands:
    def test_cmd_backup_db_prints_target(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        target = Path("backup.db")
        monkeypatch.setattr(admin, "backup_database", lambda destination: target)

        assert admin._cmd_backup_db(Namespace(destination="custom")) == 0
        assert f"Backup created: {target}" in capsys.readouterr().out

    def test_cmd_list_accounts_prints_no_accounts(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        closed = {"value": False}
        conn = SimpleNamespace(close=lambda: closed.__setitem__("value", True))
        monkeypatch.setattr(db_init, "ensure_db", lambda: conn)
        monkeypatch.setattr(admin, "list_accounts", lambda _conn: [])

        assert admin._cmd_list_accounts(Namespace()) == 0
        assert closed["value"] is True
        assert "No accounts found." in capsys.readouterr().out

    def test_cmd_list_accounts_prints_rows(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        conn = SimpleNamespace(close=lambda: None)
        monkeypatch.setattr(db_init, "ensure_db", lambda: conn)
        monkeypatch.setattr(admin, "list_accounts", lambda _conn: ["[1] acct1", "[2] acct2"])

        assert admin._cmd_list_accounts(Namespace()) == 0
        out = capsys.readouterr().out
        assert "[1] acct1" in out
        assert "[2] acct2" in out

    def test_cmd_delete_account_runs_preview(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        captured: dict[str, object] = {}
        conn = SimpleNamespace(close=lambda: captured.__setitem__("closed", True))
        monkeypatch.setattr(db_init, "ensure_db", lambda: conn)
        preview = SimpleNamespace(account_name="acct_a", descriptive_name="Account A", strategy="trend")
        monkeypatch.setattr(admin, "preview_account_deletion", lambda conn_obj, name: preview)

        args = Namespace(
            account="acct_a",
            no_backup=False,
            backup_destination=None,
            dry_run=True,
        )

        assert admin._cmd_delete_account(args) == 0
        assert captured == {"closed": True}
        output = capsys.readouterr().out
        assert "would remove all related data" in output

    def test_cmd_delete_account_backs_up_by_default(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        captured: dict[str, object] = {}
        conn = SimpleNamespace(close=lambda: captured.__setitem__("closed", True))
        monkeypatch.setattr(admin, "backup_database", lambda destination: Path("backup-before.db"))
        monkeypatch.setattr(db_init, "ensure_db", lambda: conn)
        monkeypatch.setattr(
            admin,
            "delete_account",
            lambda conn_obj, name: SimpleNamespace(name=name),
        )
        args = Namespace(
            account="acct_a",
            no_backup=False,
            backup_destination="backups",
            dry_run=False,
        )

        assert admin._cmd_delete_account(args) == 0
        assert captured == {"closed": True}
        output = capsys.readouterr().out
        assert "Backup created before delete: backup-before.db" in output
        assert "Deleted account 'acct_a'" in output

    def test_cmd_delete_account_skips_backup_when_opted_out(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        conn = SimpleNamespace(close=lambda: None)
        monkeypatch.setattr(
            admin,
            "backup_database",
            lambda destination: pytest.fail("backup_database must not run with --no-backup"),
        )
        monkeypatch.setattr(db_init, "ensure_db", lambda: conn)
        monkeypatch.setattr(
            admin,
            "delete_account",
            lambda conn_obj, name: SimpleNamespace(name=name),
        )
        args = Namespace(
            account="acct_a",
            no_backup=True,
            backup_destination=None,
            dry_run=False,
        )

        assert admin._cmd_delete_account(args) == 0
        output = capsys.readouterr().out
        assert "Backup created" not in output
        assert "Deleted account 'acct_a'" in output


class TestParserAndMain:
    def test_build_parser_registers_handlers(self) -> None:
        parser = admin.build_parser()

        backup_args = parser.parse_args(["backup-db"])
        delete_args = parser.parse_args(["delete-account", "acct1"])
        list_args = parser.parse_args(["list-accounts"])

        assert backup_args.handler is admin._cmd_backup_db
        assert delete_args.handler is admin._cmd_delete_account
        assert delete_args.no_backup is False  # backup is on unless opted out
        assert list_args.handler is admin._cmd_list_accounts

    def test_main_dispatches_handler(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parser = FakeParser(Namespace(handler=lambda _args: 7))
        monkeypatch.setattr(admin, "build_parser", lambda: parser)

        assert admin.main() == 7

    def test_main_routes_handler_errors_to_parser_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(_args: Namespace) -> int:
            raise RuntimeError("boom")

        parser = FakeParser(Namespace(handler=boom))
        monkeypatch.setattr(admin, "build_parser", lambda: parser)

        assert admin.main() == 2
        assert parser.error_message == "boom"


def test_admin_module_main_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    conn = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(db_init, "ensure_db", lambda: conn)
    monkeypatch.setattr(admin, "list_accounts", lambda _conn: [])
    monkeypatch.setattr(sys, "argv", ["admin", "list-accounts"])

    with pytest.raises(SystemExit) as excinfo:
        raise SystemExit(admin.main())

    assert excinfo.value.code == 0
