from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

from trading.database.db import ensure_db
from trading.database.db_backend import SQLiteBackend, get_backend


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


def _resolve_accounts_for_delete(conn, names: list[str], delete_all: bool) -> list[dict[str, object]]:
    if delete_all:
        rows = conn.execute("SELECT id, name FROM accounts ORDER BY name ASC").fetchall()
    else:
        placeholders = ",".join(["?"] * len(names))
        rows = conn.execute(
            f"SELECT id, name FROM accounts WHERE name IN ({placeholders}) ORDER BY name ASC",
            tuple(names),
        ).fetchall()

        found = {str(row["name"]) for row in rows}
        missing = [name for name in names if name not in found]
        if missing:
            missing_text = ", ".join(missing)
            raise ValueError(f"Accounts not found: {missing_text}")

    return [{"id": int(row["id"]), "name": str(row["name"])} for row in rows]


def _count_rows(conn, table: str, where_sql: str, params: tuple[object, ...]) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {where_sql}", params).fetchone()
    return int(row["n"])


def delete_accounts(
    *,
    account_names: list[str],
    delete_all: bool,
    dry_run: bool,
) -> dict[str, int]:
    conn = ensure_db()
    try:
        targets = _resolve_accounts_for_delete(conn, account_names, delete_all)
        if not targets:
            return {
                "accounts": 0,
                "trades": 0,
                "equity_snapshots": 0,
                "backtest_runs": 0,
                "backtest_trades": 0,
                "backtest_equity_snapshots": 0,
            }

        account_ids = tuple(int(item["id"]) for item in targets)
        account_placeholders = ",".join(["?"] * len(account_ids))

        run_rows = conn.execute(
            f"SELECT id FROM backtest_runs WHERE account_id IN ({account_placeholders})",
            account_ids,
        ).fetchall()
        run_ids = tuple(int(row["id"]) for row in run_rows)

        counts = {
            "accounts": len(targets),
            "trades": _count_rows(conn, "trades", f"account_id IN ({account_placeholders})", account_ids),
            "equity_snapshots": _count_rows(
                conn,
                "equity_snapshots",
                f"account_id IN ({account_placeholders})",
                account_ids,
            ),
            "backtest_runs": len(run_ids),
            "backtest_trades": 0,
            "backtest_equity_snapshots": 0,
        }

        if run_ids:
            run_placeholders = ",".join(["?"] * len(run_ids))
            counts["backtest_trades"] = _count_rows(
                conn,
                "backtest_trades",
                f"run_id IN ({run_placeholders})",
                run_ids,
            )
            counts["backtest_equity_snapshots"] = _count_rows(
                conn,
                "backtest_equity_snapshots",
                f"run_id IN ({run_placeholders})",
                run_ids,
            )

        if dry_run:
            return counts

        conn.execute("BEGIN")
        if run_ids:
            run_placeholders = ",".join(["?"] * len(run_ids))
            conn.execute(f"DELETE FROM backtest_equity_snapshots WHERE run_id IN ({run_placeholders})", run_ids)
            conn.execute(f"DELETE FROM backtest_trades WHERE run_id IN ({run_placeholders})", run_ids)
            conn.execute(f"DELETE FROM backtest_runs WHERE id IN ({run_placeholders})", run_ids)

        conn.execute(f"DELETE FROM equity_snapshots WHERE account_id IN ({account_placeholders})", account_ids)
        conn.execute(f"DELETE FROM trades WHERE account_id IN ({account_placeholders})", account_ids)
        conn.execute(f"DELETE FROM accounts WHERE id IN ({account_placeholders})", account_ids)
        conn.commit()

        return counts
    finally:
        conn.close()


def _print_delete_summary(action: str, counts: dict[str, int]) -> None:
    print(f"{action} summary")
    print(f"  accounts: {counts['accounts']}")
    print(f"  trades: {counts['trades']}")
    print(f"  equity_snapshots: {counts['equity_snapshots']}")
    print(f"  backtest_runs: {counts['backtest_runs']}")
    print(f"  backtest_trades: {counts['backtest_trades']}")
    print(f"  backtest_equity_snapshots: {counts['backtest_equity_snapshots']}")


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

    counts = delete_accounts(
        account_names=names,
        delete_all=bool(args.all),
        dry_run=bool(args.dry_run),
    )

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
        return int(args.handler(args))
    except Exception as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
