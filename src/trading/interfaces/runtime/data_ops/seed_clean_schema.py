"""Seed the P3 clean-schema catalog: strategies from code, default units per account.

Idempotent — safe to re-run; only missing rows are created.

Usage:
    python -m trading.interfaces.runtime.data_ops.seed_clean_schema
"""

from __future__ import annotations

import argparse

from infrastructure.database.init import db_session
from trading.services.strategy_catalog import ensure_default_units, seed_strategy_catalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed the clean-schema strategy catalog and per-account default trading units."
    )
    parser.add_argument(
        "--strategies-only",
        action="store_true",
        help="Seed only the strategies catalog; skip default-unit bootstrap.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with db_session() as conn:
        strategies_added = seed_strategy_catalog(conn)
        print(f"strategies: {strategies_added} row(s) added")
        if not args.strategies_only:
            units_created = ensure_default_units(conn)
            print(f"default units: {units_created} created")


if __name__ == "__main__":
    main()
