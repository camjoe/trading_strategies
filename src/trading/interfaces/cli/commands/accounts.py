from __future__ import annotations

import argparse
from collections.abc import Callable


def add_account_commands(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
    add_option_args: Callable[..., None],
) -> None:
    sub.add_parser("init", help="Initialize paper trading database.")
    sub.add_parser("list-accounts", help="List all paper trading accounts.")

    p_create = sub.add_parser("create-account", help="Create a new paper account.")
    p_create.add_argument("--name", required=True, help="Account name, e.g. trend_v1")
    p_create.add_argument("--strategy", required=True, help="Base strategy label")
    p_create.add_argument("--initial-cash", type=float, required=True, help="Starting cash")
    add_option_args(p_create)
    p_create.add_argument(
        "--benchmark",
        default="SPY",
        help="Benchmark ticker for this strategy account (default: SPY)",
    )

    p_set_benchmark = sub.add_parser("set-benchmark", help="Set benchmark ticker for an account.")
    p_set_benchmark.add_argument("--account", required=True, help="Account name")
    p_set_benchmark.add_argument("--benchmark", required=True, help="Benchmark ticker, e.g. SPY")

    p_configure = sub.add_parser("configure-account", help="Update per-account metadata and goals.")
    p_configure.add_argument("--account", required=True, help="Account name")
    add_option_args(p_configure, configure_mode=True)
