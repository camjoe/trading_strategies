from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from trading.database.code.csv_export import export_tables_to_csv, zip_export_directory  # noqa: E402


def main() -> int:
    result = export_tables_to_csv(
        output_base_dir=_REPO_ROOT / "local" / "exports",
    )
    zip_path = zip_export_directory(result.output_dir)

    print(f"[export] Database: {result.db_path}")
    print(f"[export] Output:   {result.output_dir}")
    for table_result in result.tables:
        print(
            f"[export] {table_result.table}: {table_result.row_count} row(s) -> {table_result.output_path.name}"
        )
    print(f"[export] Archive:  {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
