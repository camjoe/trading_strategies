from __future__ import annotations

import runpy
from pathlib import Path


def main() -> int:
    target = Path(__file__).resolve().parent / "data_ops" / "backup_db.py"
    runpy.run_path(str(target), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())