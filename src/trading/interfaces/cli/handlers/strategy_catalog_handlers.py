"""Handlers for the strategy-catalog edit commands.

Create a tuned variant of a code primitive, edit a draft strategy's knobs, or
freeze a strategy. Knob overrides are validated against the primitive's code
schema in the service layer; validation errors surface as the raised message.
"""

from __future__ import annotations

from typing import Any


def _knob_overrides(args: object) -> dict[str, str]:
    return {key: value for key, value in getattr(args, "set_knobs", []) or []}


def _describe(record: Any) -> str:
    return (
        f"primitive={record.primitive} params={record.params_json} "
        f"status={record.status} enabled={bool(record.enabled)}"
    )


def handle_create_strategy_variant(conn, args, parser, *, deps: dict[str, Any]) -> None:
    saved = deps["create_strategy_variant"](
        conn,
        strategy_key=args.strategy,
        primitive=args.primitive,
        params=_knob_overrides(args) or None,
        description=getattr(args, "description", None),
    )
    print(f"Created strategy {saved.strategy_key}: {_describe(saved)}")


def handle_configure_strategy(conn, args, parser, *, deps: dict[str, Any]) -> None:
    knobs = _knob_overrides(args)
    enabled = getattr(args, "enabled", None)
    if not knobs and enabled is None:
        parser.error("Provide --set KEY=VALUE and/or --enabled to change.")
    saved = deps["configure_strategy"](
        conn,
        strategy_key=args.strategy,
        params=knobs or None,
        enabled=enabled,
    )
    print(f"Updated strategy {saved.strategy_key}: {_describe(saved)}")


def handle_freeze_strategy(conn, args, parser, *, deps: dict[str, Any]) -> None:
    saved = deps["freeze_strategy"](conn, strategy_key=args.strategy)
    print(f"Froze strategy {saved.strategy_key}: status={saved.status}")
