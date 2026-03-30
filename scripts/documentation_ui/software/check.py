from __future__ import annotations

import argparse
from pathlib import Path

from common.repo_paths import get_repo_root
from scripts.documentation_ui.common.io import load_json
from scripts.documentation_ui.software.registry import (
    normalize_package_name,
    parse_requirements,
)


def run_software_reference_check(
    repo_root: Path,
    registry_rel_path: str = "paper_trading_ui/frontend/src/assets/software.json",
) -> int:
    registry_path = repo_root / registry_rel_path
    if not registry_path.exists():
        print(f"ERROR: registry not found: {registry_path}")
        return 2

    existing = load_json(registry_path)
    existing_packages = existing.get("packages", [])
    registry_by_name = {
        str(item.get("name")).split("[", 1)[0].lower(): item
        for item in existing_packages
        if isinstance(item.get("name"), str)
    }

    requirements_packages = parse_requirements(
        repo_root / "requirements/base.txt",
        repo_root / "requirements/dev.txt",
    )

    registry_names = set(registry_by_name)
    requirement_names = set(requirements_packages)

    missing_from_registry = sorted(requirement_names - registry_names)
    drift_issues: list[str] = []

    for name in sorted(registry_names):
        item = registry_by_name[name]
        requirement_item = requirements_packages.get(name)
        if requirement_item is None:
            drift_issues.append(f"- {item['name']}: present in registry but missing from requirements")
            continue
        if item.get("version") != requirement_item.get("version"):
            drift_issues.append(f"- {item['name']}: registry version differs from requirements")
        if item.get("scope") != requirement_item.get("scope"):
            drift_issues.append(f"- {item['name']}: registry scope differs from requirements")
        if not str(item.get("purpose") or "").strip():
            drift_issues.append(f"- {item['name']}: missing purpose")

    print("Software Reference Check")
    print(f"Registry: {registry_path.relative_to(repo_root)}")
    print(f"Packages in registry: {len(registry_by_name)}")
    print(f"Requirements packages parsed: {len(requirement_names)}")

    if not missing_from_registry and not drift_issues:
        print("\nPASS: software registry is in sync with requirements.")
        return 0

    print("\nFAIL: software registry drift detected.")
    if missing_from_registry:
        print(f"- Packages in requirements but missing from registry: {', '.join(missing_from_registry)}")
        print("  Run: python -m scripts.reference_docs.sync_all")
    if drift_issues:
        print("- Drift issues:")
        for issue in drift_issues[:20]:
            print(f"  {issue}")
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that assets/software.json is in sync with requirements files.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = get_repo_root(__file__) if args.repo_root is None else Path(args.repo_root).resolve()
    return run_software_reference_check(repo_root=repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
