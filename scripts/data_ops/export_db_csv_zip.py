from __future__ import annotations

from common.repo_paths import get_repo_root
from trading.database.csv_export import export_tables_to_csv, zip_export_directory

REPO_ROOT = get_repo_root(__file__)


def _print_export_summary(result) -> None:
    print(f"[export] Database: {result.db_path}")
    print(f"[export] Output:   {result.output_dir}")
    for table_result in result.tables:
        print(
            f"[export] {table_result.table}: {table_result.row_count} row(s) -> {table_result.output_path.name}"
        )


def main() -> int:
    result = export_tables_to_csv(
        output_base_dir=REPO_ROOT / "local" / "exports",
    )
    zip_path = zip_export_directory(result.output_dir)

    _print_export_summary(result)
    print(f"[export] Archive:  {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

