from __future__ import annotations

from trading.interfaces.cli.handlers.context import CliContext
from trading.services.parameters.presentation import show_parameters
from trading.services.promotion.actions import execute_promotion_review_action, execute_promotion_review_request
from trading.services.promotion.presentation import show_promotion_review_history, show_promotion_status
from trading.services.reporting.account import account_report
from trading.services.reporting.comparison import compare_strategies
from trading.services.reporting.concentration import show_portfolio_concentration
from trading.services.reporting.exposure import show_portfolio_exposure
from trading.services.reporting.snapshots import show_snapshots, snapshot_account


def handle_report(conn, args, parser, *, ctx: CliContext) -> None:
    account_report(conn, args.account, provider=ctx.provider)


def handle_promotion_status(conn, args, parser, *, ctx: CliContext) -> None:
    show_promotion_status(conn, args.account, args.strategy)


def handle_promotion_request_review(conn, args, parser, *, ctx: CliContext) -> None:
    review = execute_promotion_review_request(
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


def handle_promotion_review_history(conn, args, parser, *, ctx: CliContext) -> None:
    show_promotion_review_history(
        conn,
        args.account,
        args.strategy,
        limit=args.limit,
    )


def handle_promotion_review_action(conn, args, parser, *, ctx: CliContext) -> None:
    review = execute_promotion_review_action(
        conn,
        review_id=args.review_id,
        action=args.action,
        actor_name=args.actor,
        note=args.note,
    )
    print(f"Updated promotion review #{review.id} to state={review.review_state}.")


def handle_snapshot(conn, args, parser, *, ctx: CliContext) -> None:
    snapshot_account(conn, args.account, args.time, provider=ctx.provider)


def handle_snapshot_history(conn, args, parser, *, ctx: CliContext) -> None:
    show_snapshots(conn, args.account, args.limit)


def handle_portfolio_exposure(conn, args, parser, *, ctx: CliContext) -> None:
    show_portfolio_exposure(conn)


def handle_portfolio_concentration(conn, args, parser, *, ctx: CliContext) -> None:
    show_portfolio_concentration(conn)


def handle_parameters(conn, args, parser, *, ctx: CliContext) -> None:
    show_parameters(conn, args.account)


def handle_compare_strategies(conn, args, parser, *, ctx: CliContext) -> None:
    compare_strategies(conn, args.lookback, provider=ctx.provider)
