from __future__ import annotations

import argparse
from pathlib import Path

from common.repo_paths import get_repo_root
from scripts.documentation_ui.api.build_registry import run_build as build_api
from scripts.documentation_ui.software.build_registry import run_build as build_software


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync frontend/src/assets reference JSON files from live code and requirements.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    build_api(repo_root)
    build_software(repo_root)
    print("\nSync completed. finance.json is manually curated — edit it directly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
