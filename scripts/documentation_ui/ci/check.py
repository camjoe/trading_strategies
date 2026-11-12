from __future__ import annotations

import argparse
import json
from pathlib import Path

from common.git import get_repo_root
from scripts.documentation_ui.ci.registry import CI_REGISTRY_REL, WORKFLOW_REL, build_payload


def run_ci_check(repo_root: Path, registry_rel_path: str = CI_REGISTRY_REL) -> int:
    registry_path = repo_root / registry_rel_path
    if not registry_path.exists():
        print(f"ERROR: registry not found: {registry_path}")
        return 2

    expected = build_payload(repo_root)
    existing = json.loads(registry_path.read_text(encoding="utf-8"))

    print("CI Pipeline Check")
    print(f"Registry: {registry_path.relative_to(repo_root)}")

    if existing == expected:
        print(f"\nPASS: CI pipeline is in sync with {WORKFLOW_REL}.")
        return 0

    print(f"\nFAIL: CI pipeline drift detected against {WORKFLOW_REL}.")
    for key in sorted(set(existing) | set(expected)):
        if existing.get(key) != expected.get(key):
            print(f"- {key} differs")
    print("  Run: python -m scripts.documentation_ui.sync")
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that assets/ci.json is in sync with .github/workflows/ci.yml.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_ci_check(repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
