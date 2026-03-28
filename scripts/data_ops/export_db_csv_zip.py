from __future__ import annotations

from common.repo_paths import get_repo_root
from trading.interfaces.runtime.data_ops.csv_export import (
    export_tables_to_csv,
    print_export_summary,
    zip_export_directory,
)

REPO_ROOT = get_repo_root(__file__)


def main() -> int:
    result = export_tables_to_csv(
        output_base_dir=REPO_ROOT / "local" / "exports",
    )
    zip_path = zip_export_directory(result.output_dir)

    print_export_summary(result)
    print(f"[export] Archive:  {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

