from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, cast

from trading.database.db import ensure_db
from trading.database.db_backend import SQLiteBackend, get_backend
from trading.services.admin_service import delete_accounts


def _sqlite_db_path() -> Path:
    backend = get_backend()
    if not isinstance(backend, SQLiteBackend):
        raise RuntimeError("This tool currently supports only SQLite backends.")
    return backend.db_path


def _parse_account_names(raw_names: list[str]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for raw in raw_names:
        for part in str(raw).split(","):
            name = part.strip()
            if not name:
                continue
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def backup_database(destination: str | None = None) -> Path:
    source = _sqlite_db_path()
    if not source.exists():
        raise FileNotFoundError(f"Database file not found: {source}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if destination is None:
        backups_dir = source.parent / "backups"
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


def _print_delete_summary(action: str, counts: dict[str, int]) -> None:
    print(f"{action} summary")
    print(f"  accounts: {counts['accounts']}")
    print(f"  trades: {counts['trades']}")
    print(f"  equity_snapshots: {counts['equity_snapshots']}")
    print(f"  backtest_runs: {counts['backtest_runs']}")
    print(f"  backtest_trades: {counts['backtest_trades']}")
    print(f"  backtest_equity_snapshots: {counts['backtest_equity_snapshots']}")
    print(f"  walk_forward_groups: {counts['walk_forward_groups']}")
    print(f"  walk_forward_group_runs: {counts['walk_forward_group_runs']}")
    print(f"  promotion_reviews: {counts['promotion_reviews']}")
    print(f"  promotion_review_events: {counts['promotion_review_events']}")


def _cmd_backup_db(args: argparse.Namespace) -> int:
    target = backup_database(args.destination)
    print(f"Backup created: {target}")
    return 0


def _cmd_list_accounts(_args: argparse.Namespace) -> int:
    conn = ensure_db()
    try:
        rows = conn.execute("SELECT id, name, strategy, initial_cash, benchmark_ticker FROM accounts ORDER BY name ASC").fetchall()
    finally:
        conn.close()

    if not rows:
        print("No accounts found.")
        return 0

    for row in rows:
        print(
            f"[{row['id']}] {row['name']} | strategy={row['strategy']} | "
            f"initial_cash={float(row['initial_cash']):.2f} | benchmark={row['benchmark_ticker']}"
        )
    return 0


def _cmd_delete_accounts(args: argparse.Namespace) -> int:
    names = _parse_account_names(args.accounts or [])

    if args.all and not args.yes:
        raise ValueError("--all requires --yes to avoid accidental mass deletion.")

    if not args.all and not names:
        raise ValueError("Provide at least one account name, or use --all --yes.")

    if args.backup_before:
        backup_path = backup_database(args.backup_destination)
        print(f"Backup created before delete: {backup_path}")

    conn = ensure_db()
    try:
        counts = delete_accounts(
            conn,
            account_names=names,
            delete_all=bool(args.all),
            dry_run=bool(args.dry_run),
        )
    finally:
        conn.close()

    action = "Dry-run delete" if args.dry_run else "Delete"
    _print_delete_summary(action, counts)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Database admin tools for trading/database/paper_trading.db",
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

    p_delete = sub.add_parser("delete-accounts", help="Delete one or more accounts and related records.")
    p_delete.add_argument(
        "accounts",
        nargs="*",
        help="Account name(s), supports comma-separated values.",
    )
    p_delete.add_argument("--all", action="store_true", help="Delete all accounts in the database.")
    p_delete.add_argument("--yes", action="store_true", help="Required with --all to confirm mass deletion.")
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
    p_delete.set_defaults(handler=_cmd_delete_accounts)

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
