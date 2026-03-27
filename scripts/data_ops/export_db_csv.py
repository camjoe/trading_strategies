from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BOOTSTRAP_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_BOOTSTRAP_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_REPO_ROOT))

REPO_ROOT = _BOOTSTRAP_REPO_ROOT

from trading.database.csv_export import DEFAULT_EXPORT_TABLES, export_tables_to_csv  # noqa: E402


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


def print_export_summary(result) -> None:
    print(f"[export] Database: {result.db_path}")
    print(f"[export] Output:   {result.output_dir}")
    for table_result in result.tables:
        print(
            f"[export] {table_result.table}: {table_result.row_count} row(s) -> {table_result.output_path.name}"
        )


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

