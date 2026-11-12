from __future__ import annotations

import argparse
import json
from pathlib import Path

from common.git import get_repo_root
from scripts.documentation_ui.overview.registry import OVERVIEW_REGISTRY_REL, build_payload


def run_overview_check(repo_root: Path, registry_rel_path: str = OVERVIEW_REGISTRY_REL) -> int:
    registry_path = repo_root / registry_rel_path
    if not registry_path.exists():
        print(f"ERROR: registry not found: {registry_path}")
        return 2

    expected = build_payload(repo_root)
    existing = json.loads(registry_path.read_text(encoding="utf-8"))

    print("Overview Facts Check")
    print(f"Registry: {registry_path.relative_to(repo_root)}")

    if existing == expected:
        print("\nPASS: overview facts are in sync with the repository.")
        return 0

    print("\nFAIL: overview facts drift detected.")
    for key in sorted(set(existing) | set(expected)):
        if existing.get(key) != expected.get(key):
            print(f"- {key}: registry {existing.get(key)!r}, repository {expected.get(key)!r}")
    print("  Run: python -m scripts.documentation_ui.sync")
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that assets/overview.json is in sync with the repository.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = get_repo_root(__file__) if args.repo_root is None else Path(args.repo_root).resolve()
    return run_overview_check(repo_root=repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
