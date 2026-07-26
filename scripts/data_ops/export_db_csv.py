from __future__ import annotations

import argparse
import sys
from pathlib import Path

from trading.interfaces.runtime.data_ops.csv_export import open_db_connection
from trading.services.table_export import DEFAULT_EXPORT_TABLES, stream_table_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print or save one SQLite table as CSV, generated on demand from the current database.",
    )
    parser.add_argument(
        "--table",
        required=True,
        help=f"Table to export. Commonly one of: {','.join(DEFAULT_EXPORT_TABLES)}.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output file path. Defaults to stdout.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    conn, db_path = open_db_connection()
    try:
        chunks = stream_table_csv(conn, args.table)
        if args.out:
            output_path = Path(args.out).expanduser()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", newline="", encoding="utf-8") as fh:
                for chunk in chunks:
                    fh.write(chunk)
            print(f"[export] {db_path} -> {output_path} ({args.table})", file=sys.stderr)
        else:
            for chunk in chunks:
                sys.stdout.write(chunk)
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
