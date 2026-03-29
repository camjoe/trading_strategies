from __future__ import annotations

import argparse
from pathlib import Path

from common.repo_paths import get_repo_root
from scripts.documentation_ui.common.io import load_json
from scripts.documentation_ui.software.registry import parse_markdown, parse_requirements, parse_ui_packages


def run_software_reference_check(repo_root: Path, registry_rel_path: str = "docs/reference/software.json") -> int:
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

    requirements_packages = parse_requirements(repo_root / "requirements/base.txt", repo_root / "requirements/dev.txt")
    markdown_packages = parse_markdown(repo_root / "docs/reference/Software.md")
    ui_packages = parse_ui_packages(repo_root / "paper_trading_ui/frontend/src/views/docs.html")

    registry_names = set(registry_by_name)
    requirement_names = set(requirements_packages)
    markdown_names = set(markdown_packages)
    ui_names = set(ui_packages)

    missing_from_registry = sorted(requirement_names - registry_names)
    drift_issues: list[str] = []

    for name in sorted(registry_names):
        item = registry_by_name[name]
        requirement_item = requirements_packages.get(name)
        markdown_item = markdown_packages.get(name)
        ui_item = ui_packages.get(name)
        if requirement_item is None:
            drift_issues.append(f"- {item['name']}: present in registry but missing from requirements")
            continue
        if item.get("version") != requirement_item.get("version"):
            drift_issues.append(f"- {item['name']}: registry version differs from requirements")
        if item.get("scope") != requirement_item.get("scope"):
            drift_issues.append(f"- {item['name']}: registry scope differs from requirements")
        if not str(item.get("purpose") or "").strip():
            drift_issues.append(f"- {item['name']}: missing purpose")

        if markdown_item is None:
            drift_issues.append(f"- {item['name']}: missing from Software.md")
        else:
            if markdown_item.get("version") != item.get("version"):
                drift_issues.append(f"- {item['name']}: markdown version differs from registry")
            if markdown_item.get("scope") != item.get("scope"):
                drift_issues.append(f"- {item['name']}: markdown scope differs from registry")
            if markdown_item.get("purpose") != item.get("purpose"):
                drift_issues.append(f"- {item['name']}: markdown purpose differs from registry")
            if markdown_item.get("group") != item.get("group"):
                drift_issues.append(f"- {item['name']}: markdown group differs from registry")

        if ui_item is None:
            drift_issues.append(f"- {item['name']}: missing from docs.html Software section")
        else:
            if ui_item.get("purpose") != item.get("purpose"):
                drift_issues.append(f"- {item['name']}: UI purpose differs from registry")
            if ui_item.get("group") != item.get("group"):
                drift_issues.append(f"- {item['name']}: UI group differs from registry")

    extra_in_markdown = sorted(markdown_names - registry_names)
    extra_in_ui = sorted(ui_names - registry_names)

    print("Software Reference Check")
    print(f"Repo root: {repo_root}")
    print(f"Registry: {registry_path}")
    print(f"Packages in registry: {len(registry_by_name)}")
    print(f"Requirements packages parsed: {len(requirement_names)}")
    print(f"Markdown packages parsed: {len(markdown_names)}")
    print(f"UI packages parsed: {len(ui_names)}")

    if not missing_from_registry and not extra_in_markdown and not extra_in_ui and not drift_issues:
        print("\nPASS: software reference is in sync with requirements, markdown, and UI docs.")
        return 0

    print("\nFAIL: software reference drift detected.")
    if missing_from_registry:
        print(f"- Packages present in requirements but missing from registry: {', '.join(missing_from_registry[:10])}")
    if extra_in_markdown:
        print(f"- Packages present in markdown but missing from registry: {', '.join(extra_in_markdown[:10])}")
    if extra_in_ui:
        print(f"- Packages present in UI docs but missing from registry: {', '.join(extra_in_ui[:10])}")
    if drift_issues:
        print("- Drift issues (first 20):")
        for issue in drift_issues[:20]:
            print(f"  {issue}")

    print("\nUpdate the registry and/or source docs, then re-run checks.")
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate docs/reference/software.json against requirements, markdown, and UI docs.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    parser.add_argument("--registry", default="docs/reference/software.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_software_reference_check(repo_root=repo_root, registry_rel_path=args.registry)


if __name__ == "__main__":
    raise SystemExit(main())