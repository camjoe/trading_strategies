from __future__ import annotations

import argparse
import json
from pathlib import Path

from common.git import get_repo_root
from scripts.documentation_ui.overview.registry import OVERVIEW_REGISTRY_REL, build_payload


def run_build(repo_root: Path, registry_rel_path: str = OVERVIEW_REGISTRY_REL) -> None:
    """Write the repository facts shown on the About page."""
    registry_path = repo_root / registry_rel_path
    payload = build_payload(repo_root)
    registry_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote overview facts: {registry_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build apps/paper_trading_web/frontend/src/assets/overview.json from the repository.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    parser.add_argument("--registry", default=OVERVIEW_REGISTRY_REL)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    run_build(repo_root, args.registry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
