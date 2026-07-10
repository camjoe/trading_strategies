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
from trading.services.parameters import ROTATION_POLICY_FIELDS


def _merged(args: object, current: object, field_names: tuple[str, ...]) -> dict[str, Any]:
    return {name: getattr(args, name, getattr(current, name)) for name in field_names}


def _require_any_flag(args: object, parser, field_names: tuple[str, ...], what: str) -> None:
    if not any(hasattr(args, name) for name in field_names):
        parser.error(f"Provide at least one {what} flag to change.")


_THROTTLE_FIELDS = (
    "max_trades_per_day",
    "max_trades_per_minute",
)


def handle_configure_throttle(conn, args, parser, *, deps: dict[str, Any]) -> None:
    _require_any_flag(args, parser, _THROTTLE_FIELDS, "throttle")
    current = deps["fetch_runtime_throttle_settings"](conn)
    values = _merged(args, current, _THROTTLE_FIELDS)
    deps["set_runtime_throttle_settings"](
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


def handle_configure_evaluation(conn, args, parser, *, deps: dict[str, Any]) -> None:
    _require_any_flag(args, parser, _EVALUATION_FIELDS, "evaluation")
    current = deps["fetch_evaluation_confidence_settings"](conn)
    values = _merged(args, current, _EVALUATION_FIELDS)
    deps["set_evaluation_confidence_settings"](conn, updated_at=utc_now_iso(), **values)
    rendered = " ".join(f"{name}={value}" for name, value in values.items())
    print(f"Updated global evaluation confidence settings: {rendered}")


def handle_configure_book_rotation_policy(conn, args, parser, *, deps: dict[str, Any]) -> None:
    _require_any_flag(args, parser, ROTATION_POLICY_FIELDS, "rotation policy")
    updates = {name: getattr(args, name) for name in ROTATION_POLICY_FIELDS if hasattr(args, name)}
    saved = deps["update_book_rotation_policy"](
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


def handle_configure_promotion(conn, args, parser, *, deps: dict[str, Any]) -> None:
    _require_any_flag(args, parser, _PROMOTION_FIELDS, "promotion")
    current = deps["fetch_promotion_policy_settings"](conn)
    values = _merged(args, current, _PROMOTION_FIELDS)
    deps["set_promotion_policy_settings"](conn, updated_at=utc_now_iso(), **values)
    rendered = " ".join(f"{name}={value}" for name, value in values.items())
    print(f"Updated global promotion policy settings: {rendered}")
