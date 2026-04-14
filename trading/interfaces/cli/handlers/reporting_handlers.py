from __future__ import annotations

from typing import Any


def handle_report(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    deps["account_report"](conn, args.account)


def handle_promotion_status(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    deps["show_promotion_status"](conn, args.account, args.strategy)


def handle_promotion_request_review(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    review = deps["execute_promotion_review_request"](
        conn,
        account_name=args.account,
        strategy_name=args.strategy,
        requested_by=args.requested_by,
        note=args.note,
    )
    print(
        f"Created promotion review #{review.id} for "
        f"{review.account_name_snapshot}/{review.strategy_name} with state={review.review_state}."
    )


def handle_promotion_review_history(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    deps["show_promotion_review_history"](
        conn,
        args.account,
        args.strategy,
        limit=args.limit,
    )


def handle_promotion_review_action(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    review = deps["execute_promotion_review_action"](
        conn,
        review_id=args.review_id,
        action=args.action,
        actor_name=args.actor,
        note=args.note,
    )
    print(f"Updated promotion review #{review.id} to state={review.review_state}.")


def handle_snapshot(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    deps["snapshot_account"](conn, args.account, args.time)


def handle_snapshot_history(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    deps["show_snapshots"](conn, args.account, args.limit)


def handle_compare_strategies(conn, args, parser, *, deps: dict[str, Any], module_file: str, db_path: str) -> None:
    deps["compare_strategies"](conn, args.lookback)
