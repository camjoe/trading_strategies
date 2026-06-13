from argparse import Namespace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.trading.interfaces.helpers import run_module_as_main

from trading.database.db_backend import SQLiteBackend, get_backend, set_backend
from trading.database.db_init import ensure_db
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


class TestParseAccountNames:
    def test_parse_account_names_splits_deduplicates_and_strips(self) -> None:
        names = admin._parse_account_names(["acct_a, acct_b", "acct_b", " acct_c ", ""])

        assert names == ["acct_a", "acct_b", "acct_c"]


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
        ensure_db().close()
        monkeypatch.setattr(admin, "datetime", FixedDateTime)
        monkeypatch.setattr(admin, "DB_BACKUPS_DIR", tmp_path / "db_backups")

        backup = admin.backup_database()

        assert backup.exists()
        assert backup.name.startswith("paper_trading_20260327_080910")
        assert backup.parent == tmp_path / "db_backups"

    def test_backup_database_accepts_explicit_file_destination(
        self, configured_backend: SQLiteBackend, tmp_path: Path
    ) -> None:
        ensure_db().close()
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
        ensure_db().close()
        monkeypatch.setattr(admin, "datetime", FixedDateTime)

        backup = admin.backup_database(str(tmp_path / "manual_backups"))

        assert backup.parent == tmp_path / "manual_backups"
        assert backup.name == "paper_trading_20260327_080910.db"
        assert backup.exists()


class TestHelpersAndCommands:
    def test_print_delete_summary_outputs_sorted_counts(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        monkeypatch.setattr(admin, "iter_delete_count_items", lambda counts: [("accounts", 1), ("orders", 2)])

        admin._print_delete_summary("Delete", {"orders": 2, "accounts": 1})

        output = capsys.readouterr().out
        assert "Delete summary" in output
        assert "accounts: 1" in output
        assert "orders: 2" in output

    def test_cmd_backup_db_prints_target(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        target = Path("backup.db")
        monkeypatch.setattr(admin, "backup_database", lambda destination: target)

        assert admin._cmd_backup_db(Namespace(destination="custom")) == 0
        assert f"Backup created: {target}" in capsys.readouterr().out

    def test_cmd_list_accounts_prints_no_accounts(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        closed = {"value": False}
        conn = SimpleNamespace(close=lambda: closed.__setitem__("value", True))
        monkeypatch.setattr(admin, "ensure_db", lambda: conn)
        monkeypatch.setattr(admin, "list_accounts", lambda _conn: [])

        assert admin._cmd_list_accounts(Namespace()) == 0
        assert closed["value"] is True
        assert "No accounts found." in capsys.readouterr().out

    def test_cmd_list_accounts_prints_rows(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        conn = SimpleNamespace(close=lambda: None)
        monkeypatch.setattr(admin, "ensure_db", lambda: conn)
        monkeypatch.setattr(admin, "list_accounts", lambda _conn: ["[1] acct1", "[2] acct2"])

        assert admin._cmd_list_accounts(Namespace()) == 0
        out = capsys.readouterr().out
        assert "[1] acct1" in out
        assert "[2] acct2" in out

    def test_cmd_delete_accounts_runs_backup_and_delete(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        captured: dict[str, object] = {}
        conn = SimpleNamespace(close=lambda: captured.__setitem__("closed", True))
        monkeypatch.setattr(admin, "backup_database", lambda destination: Path("backup-before.db"))
        monkeypatch.setattr(admin, "ensure_db", lambda: conn)

        def fake_delete_accounts(conn_obj, *, account_names, delete_all, dry_run):
            captured["conn"] = conn_obj
            captured["account_names"] = account_names
            captured["delete_all"] = delete_all
            captured["dry_run"] = dry_run
            return {"accounts": 2}

        monkeypatch.setattr(admin, "delete_accounts", fake_delete_accounts)

        args = Namespace(
            accounts=["acct_a, acct_b", "acct_b"],
            all=False,
            yes=False,
            backup_before=True,
            backup_destination="backups",
            dry_run=True,
        )

        assert admin._cmd_delete_accounts(args) == 0
        assert captured == {
            "closed": True,
            "conn": conn,
            "account_names": ["acct_a", "acct_b"],
            "delete_all": False,
            "dry_run": True,
        }
        output = capsys.readouterr().out
        assert "Backup created before delete: backup-before.db" in output
        assert "Dry-run delete summary" in output


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


class TestParserAndMain:
    def test_build_parser_registers_handlers(self) -> None:
        parser = admin.build_parser()

        backup_args = parser.parse_args(["backup-db"])
        delete_args = parser.parse_args(["delete-accounts", "acct1"])
        list_args = parser.parse_args(["list-accounts"])

        assert backup_args.handler is admin._cmd_backup_db
        assert delete_args.handler is admin._cmd_delete_accounts
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
    monkeypatch.setattr(admin, "ensure_db", lambda: conn)
    monkeypatch.setattr(admin, "list_accounts", lambda _conn: [])
    monkeypatch.setattr(sys, "argv", ["admin", "list-accounts"])

    with pytest.raises(SystemExit) as excinfo:
        raise SystemExit(admin.main())

    assert excinfo.value.code == 0
