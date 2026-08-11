"""Handlers for the operational-settings edit commands.

Each command merges the provided flags over the current effective settings
(flags built with ``argparse.SUPPRESS`` are absent when omitted), so a
partial edit never resets other fields. Every command requires at least one
flag: a zero-flag invocation would silently persist the current effective
values (pinning code defaults into the DB) rather than being a no-op.
"""

from __future__ import annotations

from typing import Any

from common.time import utc_now_iso
from trading.interfaces.cli.handlers.context import CliContext
from trading.services.operational_settings import (
    fetch_evaluation_confidence_settings,
    fetch_promotion_policy_settings,
    fetch_runtime_throttle_settings,
    set_evaluation_confidence_settings,
    set_promotion_policy_settings,
    set_runtime_throttle_settings,
    show_global_settings_history,
)
from trading.services.parameters import (
    ROTATION_POLICY_FIELDS,
    show_book_rotation_history,
    update_book_rotation_policy,
    update_book_rotation_scheduling,
)


def _merged(args: object, current: object, field_names: tuple[str, ...]) -> dict[str, Any]:
    return {name: getattr(args, name, getattr(current, name)) for name in field_names}


def _require_any_flag(args: object, parser, field_names: tuple[str, ...], what: str) -> None:
    if not any(hasattr(args, name) for name in field_names):
        parser.error(f"Provide at least one {what} flag to change.")


_THROTTLE_FIELDS = (
    "max_trades_per_day",
    "max_trades_per_minute",
)


def handle_configure_throttle(conn, args, parser, *, ctx: CliContext) -> None:
    _require_any_flag(args, parser, _THROTTLE_FIELDS, "throttle")
    current = fetch_runtime_throttle_settings(conn)
    values = _merged(args, current, _THROTTLE_FIELDS)
    set_runtime_throttle_settings(
        conn,
        runtime_max_trades_per_day=values["max_trades_per_day"],
        runtime_max_trades_per_minute=values["max_trades_per_minute"],
        updated_at=utc_now_iso(),
    )
    rendered = " ".join(f"{name}={'none' if value is None else value}" for name, value in values.items())
    print(f"Updated global trade throttle: {rendered}")


_EVALUATION_FIELDS = (
    "backtest_trade_count_for_full_confidence",
    "backtest_snapshot_count_for_full_confidence",
    "paper_live_snapshot_count_for_full_confidence",
    "backtest_trade_confidence_weight",
    "backtest_snapshot_confidence_weight",
    "backtest_evidence_weight",
    "paper_live_evidence_weight",
)


def handle_configure_evaluation(conn, args, parser, *, ctx: CliContext) -> None:
    _require_any_flag(args, parser, _EVALUATION_FIELDS, "evaluation")
    current = fetch_evaluation_confidence_settings(conn)
    values = _merged(args, current, _EVALUATION_FIELDS)
    set_evaluation_confidence_settings(conn, updated_at=utc_now_iso(), **values)
    rendered = " ".join(f"{name}={value}" for name, value in values.items())
    print(f"Updated global evaluation confidence settings: {rendered}")


# CLI flag name → book_rotation_settings scheduling field (book-owned, ADR 014).
_ROTATION_SCHEDULING_ARG_TO_FIELD = {
    "enabled": "rotation_enabled",
    "schedule": "rotation_schedule",
    "lookback_days": "rotation_lookback_days",
}


def handle_configure_book_rotation(conn, args, parser, *, ctx: CliContext) -> None:
    _require_any_flag(args, parser, tuple(_ROTATION_SCHEDULING_ARG_TO_FIELD), "rotation scheduling")
    updates = {
        field: getattr(args, arg_name)
        for arg_name, field in _ROTATION_SCHEDULING_ARG_TO_FIELD.items()
        if hasattr(args, arg_name)
    }
    saved = update_book_rotation_scheduling(
        conn,
        account_name=args.account,
        book_name=args.book,
        updates=updates,
    )
    rendered = " ".join(
        f"{field}={'none' if getattr(saved, field) is None else getattr(saved, field)}"
        for field in _ROTATION_SCHEDULING_ARG_TO_FIELD.values()
    )
    print(f"Updated rotation scheduling for book_id={saved.book_id}: {rendered}")


def handle_configure_book_rotation_policy(conn, args, parser, *, ctx: CliContext) -> None:
    _require_any_flag(args, parser, ROTATION_POLICY_FIELDS, "rotation policy")
    updates = {name: getattr(args, name) for name in ROTATION_POLICY_FIELDS if hasattr(args, name)}
    saved = update_book_rotation_policy(
        conn,
        account_name=args.account,
        book_name=args.book,
        updates=updates,
    )
    rendered = " ".join(
        f"{name}={'none' if getattr(saved, name) is None else getattr(saved, name)}" for name in ROTATION_POLICY_FIELDS
    )
    print(f"Updated rotation policy for book_id={saved.book_id}: {rendered}")


_PROMOTION_FIELDS = (
    "min_research_backtest_trade_count",
    "min_research_backtest_snapshot_count",
    "min_research_backtest_return_pct",
    "min_research_max_drawdown_pct",
    "min_research_walk_forward_average_return_pct",
    "min_live_paper_snapshot_count",
    "min_live_overall_confidence",
)


def handle_configure_promotion(conn, args, parser, *, ctx: CliContext) -> None:
    _require_any_flag(args, parser, _PROMOTION_FIELDS, "promotion")
    current = fetch_promotion_policy_settings(conn)
    values = _merged(args, current, _PROMOTION_FIELDS)
    set_promotion_policy_settings(conn, updated_at=utc_now_iso(), **values)
    rendered = " ".join(f"{name}={value}" for name, value in values.items())
    print(f"Updated global promotion policy settings: {rendered}")


def handle_settings_history(conn, args, parser, *, ctx: CliContext) -> None:
    show_global_settings_history(conn, limit=args.limit)


def handle_book_rotation_history(conn, args, parser, *, ctx: CliContext) -> None:
    show_book_rotation_history(conn, account_name=args.account, book_name=args.book, limit=args.limit)
