from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, cast

from common.paths.project_paths import DB_BACKUPS_DIR
from infrastructure.database.init import db_session
from infrastructure.database.backend import SQLiteBackend, get_backend
from trading.services.accounts import delete_account, preview_account_deletion
from trading.services.accounts.listing import list_accounts


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

    shutil.copy2(source, target)
    return target


def _cmd_backup_db(args: argparse.Namespace) -> int:
    target = backup_database(args.destination)
    print(f"Backup created: {target}")
    return 0


def _cmd_list_accounts(_args: argparse.Namespace) -> int:
    with db_session() as conn:
        lines = list_accounts(conn)
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

    if args.backup_before and not args.dry_run:
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
        "--backup-before",
        action="store_true",
        help="Create a DB backup before deleting accounts.",
    )
    p_delete.add_argument(
        "--backup-destination",
        default=None,
        help="Optional backup destination path when using --backup-before.",
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
