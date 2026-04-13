from __future__ import annotations

from typing import Any


def handle_report(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    deps["account_report"](conn, args.account)


def handle_promotion_status(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    deps["show_promotion_status"](conn, args.account, args.strategy)


def handle_snapshot(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    deps["snapshot_account"](conn, args.account, args.time)


def handle_snapshot_history(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    deps["show_snapshots"](conn, args.account, args.limit)


def handle_compare_strategies(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    deps["compare_strategies"](conn, args.lookback)
