from __future__ import annotations

import argparse
from pathlib import Path

from common.repo_paths import get_repo_root
from trading.interfaces.runtime.data_ops.csv_export import (
    DEFAULT_EXPORT_TABLES,
    export_tables_to_csv,
    print_export_summary,
)

REPO_ROOT = get_repo_root(__file__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export selected SQLite tables to timestamped CSV files.",
    )
    parser.add_argument(
        "--tables",
        default=",".join(DEFAULT_EXPORT_TABLES),
        help="Comma-separated table list. Default: accounts,equity_snapshots,trades,backtest_runs,backtest_trades",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "local" / "exports"),
        help="Base output directory where timestamped export folders are created.",
    )
    return parser.parse_args()


def _parse_table_list(raw: str) -> list[str]:
    tables = [part.strip() for part in raw.split(",") if part.strip()]
    if not tables:
        raise ValueError("At least one table must be provided.")
    return tables


def main() -> int:
    args = parse_args()
    tables = _parse_table_list(args.tables)
    output_dir = Path(args.output_dir).expanduser()

    result = export_tables_to_csv(
        tables=tables,
        output_base_dir=output_dir,
    )

    print_export_summary(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

