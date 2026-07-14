from __future__ import annotations

import argparse

from trading.interfaces.cli.commands.settings import bool_flag


def knob_assignment(raw: str) -> tuple[str, str]:
    """Argparse type for a ``KEY=VALUE`` knob override."""
    key, sep, value = raw.partition("=")
    if not sep or not key.strip():
        raise argparse.ArgumentTypeError(f"expected KEY=VALUE, got {raw!r}")
    return key.strip(), value.strip()


def add_strategy_catalog_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p_variant = sub.add_parser(
        "create-strategy-variant",
        help="Create a new draft strategy variant of a code primitive with tuned knobs.",
    )
    p_variant.add_argument("--strategy", required=True, help="New strategy key")
    p_variant.add_argument("--primitive", required=True, help="Code primitive the variant runs")
    p_variant.add_argument(
        "--set",
        action="append",
        dest="set_knobs",
        type=knob_assignment,
        metavar="KEY=VALUE",
        default=argparse.SUPPRESS,
        help="Set a knob override (repeatable)",
    )
    p_variant.add_argument("--description", default=argparse.SUPPRESS, help="Optional description")

    p_configure = sub.add_parser(
        "configure-strategy",
        help="Edit a draft strategy's knobs and/or enabled flag (untouched knobs are kept).",
    )
    p_configure.add_argument("--strategy", required=True, help="Strategy key")
    p_configure.add_argument(
        "--set",
        action="append",
        dest="set_knobs",
        type=knob_assignment,
        metavar="KEY=VALUE",
        default=argparse.SUPPRESS,
        help="Set a knob override (repeatable)",
    )
    p_configure.add_argument(
        "--enabled",
        type=bool_flag,
        default=argparse.SUPPRESS,
        help="Whether the strategy is enabled (true/false)",
    )

    p_freeze = sub.add_parser(
        "freeze-strategy",
        help="Freeze a draft strategy (one-way; tuning it afterward requires a new variant).",
    )
    p_freeze.add_argument("--strategy", required=True, help="Strategy key")
