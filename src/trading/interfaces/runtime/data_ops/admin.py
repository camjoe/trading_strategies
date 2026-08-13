from __future__ import annotations

import argparse
import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import cast

from common.paths import DB_BACKUPS_DIR
from infrastructure.database.backend import SQLiteBackend, get_backend
from infrastructure.database.connection import db_session
from trading.services.accounts import delete_account, preview_account_deletion
from trading.services.accounts.listing import fetch_account_listing_lines


def _sqlite_db_path() -> Path:
    backend = get_backend()
    if not isinstance(backend, SQLiteBackend):
        raise RuntimeError("This tool currently supports only SQLite backends.")
    return backend.db_path


def backup_database(destination: str | None = None) -> Path:
    source = _sqlite_db_path()
    if not source.exists():
        raise FileNotFoundError(f"Database file not found: {source}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if destination is None:
        backups_dir = DB_BACKUPS_DIR
        backups_dir.mkdir(parents=True, exist_ok=True)
        target = backups_dir / f"{source.stem}_{stamp}.db"
    else:
        raw_target = Path(destination)
        if raw_target.suffix.lower() == ".db":
            raw_target.parent.mkdir(parents=True, exist_ok=True)
            target = raw_target
        else:
            raw_target.mkdir(parents=True, exist_ok=True)
            target = raw_target / f"{source.stem}_{stamp}.db"

    # Not a file copy: in WAL mode, commits live in the -wal sidecar until a
    # checkpoint, so copying the .db alone silently drops them. backup() reads
    # through the WAL and stays consistent under a live writer.
    with (
        closing(sqlite3.connect(source)) as source_conn,
        closing(sqlite3.connect(target)) as target_conn,
    ):
        source_conn.backup(target_conn)
    return target


def _cmd_backup_db(args: argparse.Namespace) -> int:
    target = backup_database(args.destination)
    print(f"Backup created: {target}")
    return 0


def _cmd_list_accounts(_args: argparse.Namespace) -> int:
    with db_session() as conn:
        lines = fetch_account_listing_lines(conn)
    if not lines:
        print("No accounts found.")
        return 0
    for line in lines:
        print(line)
    return 0


def _cmd_delete_account(args: argparse.Namespace) -> int:
    account_name = str(args.account).strip()
    if not account_name:
        raise ValueError("Provide an account name.")

    # Deletion cascades everything the account owns; the pre-delete backup is
    # the only retention path, so it is on by default.
    if not args.no_backup and not args.dry_run:
        backup_path = backup_database(args.backup_destination)
        print(f"Backup created before delete: {backup_path}")

    with db_session() as conn:
        if args.dry_run:
            preview = preview_account_deletion(conn, account_name)
            print(
                f"Deleting account '{preview.account_name}' "
                f"({preview.descriptive_name}, strategy: {preview.strategy}) "
                "would remove all related data."
            )
        else:
            deleted = delete_account(conn, account_name)
            print(f"Deleted account '{deleted.name}' and its related rows.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Database admin tools (DB path: local/paper_trading.db by default; configurable via TRADING_DB_PATH)"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list-accounts", help="List current accounts in the DB.")
    p_list.set_defaults(handler=_cmd_list_accounts)

    p_backup = sub.add_parser("backup-db", help="Create a timestamped backup of the database.")
    p_backup.add_argument(
        "destination",
        nargs="?",
        default=None,
        help="Optional target file path (.db) or directory for the backup.",
    )
    p_backup.set_defaults(handler=_cmd_backup_db)

    p_delete = sub.add_parser("delete-account", help="Delete one account and its related records.")
    p_delete.add_argument(
        "account",
        help="Account name.",
    )
    p_delete.add_argument("--dry-run", action="store_true", help="Show what would be deleted without changes.")
    p_delete.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip the automatic pre-delete database backup (deletion is unrecoverable without it).",
    )
    p_delete.add_argument(
        "--backup-destination",
        default=None,
        help="Optional destination path for the automatic pre-delete backup.",
    )
    p_delete.set_defaults(handler=_cmd_delete_account)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        handler = cast(Callable[[argparse.Namespace], int], args.handler)
        return handler(args)
    except Exception as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
