from __future__ import annotations

import argparse
from pathlib import Path

from common.repo_paths import get_repo_root
from scripts.documentation_ui.common.io import load_json
from scripts.documentation_ui.software.registry import (
    normalize_language_name,
    normalize_project_name,
    parse_markdown,
    parse_markdown_languages,
    parse_markdown_projects,
    parse_requirements,
    parse_ui_languages,
    parse_ui_packages,
    parse_ui_projects,
)


def run_software_reference_check(repo_root: Path, registry_rel_path: str = "docs/reference/software.json") -> int:
    registry_path = repo_root / registry_rel_path
    if not registry_path.exists():
        print(f"ERROR: registry not found: {registry_path}")
        return 2

    existing = load_json(registry_path)
    existing_packages = existing.get("packages", [])
    existing_projects = existing.get("projects", [])
    existing_languages = existing.get("languages_frameworks", [])
    registry_by_name = {
        str(item.get("name")).split("[", 1)[0].lower(): item
        for item in existing_packages
        if isinstance(item.get("name"), str)
    }
    registry_projects_by_name = {
        normalize_project_name(str(item.get("name"))): item
        for item in existing_projects
        if isinstance(item.get("name"), str)
    }
    registry_languages_by_name = {
        normalize_language_name(str(item.get("name"))): item
        for item in existing_languages
        if isinstance(item.get("name"), str)
    }

    requirements_packages = parse_requirements(repo_root / "requirements/base.txt", repo_root / "requirements/dev.txt")
    markdown_packages = parse_markdown(repo_root / "docs/reference/Software.md")
    ui_packages = parse_ui_packages(repo_root / "paper_trading_ui/frontend/src/views/docs.html")
    markdown_projects = parse_markdown_projects(repo_root / "docs/reference/Software.md")
    ui_projects = parse_ui_projects(repo_root / "paper_trading_ui/frontend/src/views/docs.html")
    markdown_languages = parse_markdown_languages(repo_root / "docs/reference/Software.md")
    ui_languages = parse_ui_languages(repo_root / "paper_trading_ui/frontend/src/views/docs.html")

    registry_names = set(registry_by_name)
    registry_project_names = set(registry_projects_by_name)
    registry_language_names = set(registry_languages_by_name)
    requirement_names = set(requirements_packages)
    markdown_names = set(markdown_packages)
    ui_names = set(ui_packages)
    markdown_project_names = set(markdown_projects)
    ui_project_names = set(ui_projects)
    markdown_language_names = set(markdown_languages)
    ui_language_names = set(ui_languages)

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

    project_drift_issues: list[str] = []
    for name in sorted(registry_project_names):
        registry_item = registry_projects_by_name[name]
        markdown_item = markdown_projects.get(name)
        ui_item = ui_projects.get(name)

        if markdown_item is None:
            project_drift_issues.append(f"- {registry_item['name']}: missing from Software.md projects table")
        elif markdown_item.get("description") != registry_item.get("description"):
            project_drift_issues.append(f"- {registry_item['name']}: markdown description differs from registry")

        if ui_item is None:
            project_drift_issues.append(f"- {registry_item['name']}: missing from docs.html projects table")
        elif ui_item.get("description") != registry_item.get("description"):
            project_drift_issues.append(f"- {registry_item['name']}: UI description differs from registry")

    extra_projects_in_markdown = sorted(markdown_project_names - registry_project_names)
    extra_projects_in_ui = sorted(ui_project_names - registry_project_names)

    language_drift_issues: list[str] = []
    for name in sorted(registry_language_names):
        registry_item = registry_languages_by_name[name]
        markdown_item = markdown_languages.get(name)
        ui_item = ui_languages.get(name)

        if markdown_item is None:
            language_drift_issues.append(
                f"- {registry_item['name']}: missing from Software.md languages/frameworks table"
            )
        elif markdown_item.get("usage") != registry_item.get("usage"):
            language_drift_issues.append(f"- {registry_item['name']}: markdown usage differs from registry")

        if ui_item is None:
            language_drift_issues.append(f"- {registry_item['name']}: missing from docs.html languages/frameworks table")
        elif ui_item.get("usage") != registry_item.get("usage"):
            language_drift_issues.append(f"- {registry_item['name']}: UI usage differs from registry")

    extra_languages_in_markdown = sorted(markdown_language_names - registry_language_names)
    extra_languages_in_ui = sorted(ui_language_names - registry_language_names)

    print("Software Reference Check")
    print(f"Repo root: {repo_root}")
    print(f"Registry: {registry_path}")
    print(f"Packages in registry: {len(registry_by_name)}")
    print(f"Projects in registry: {len(registry_projects_by_name)}")
    print(f"Languages/frameworks in registry: {len(registry_languages_by_name)}")
    print(f"Requirements packages parsed: {len(requirement_names)}")
    print(f"Markdown packages parsed: {len(markdown_names)}")
    print(f"UI packages parsed: {len(ui_names)}")
    print(f"Markdown projects parsed: {len(markdown_project_names)}")
    print(f"UI projects parsed: {len(ui_project_names)}")
    print(f"Markdown languages/frameworks parsed: {len(markdown_language_names)}")
    print(f"UI languages/frameworks parsed: {len(ui_language_names)}")

    if (
        not missing_from_registry
        and not extra_in_markdown
        and not extra_in_ui
        and not drift_issues
        and not project_drift_issues
        and not extra_projects_in_markdown
        and not extra_projects_in_ui
        and not language_drift_issues
        and not extra_languages_in_markdown
        and not extra_languages_in_ui
    ):
        print("\nPASS: software reference is in sync with requirements, markdown, and UI docs.")
        return 0

    print("\nFAIL: software reference drift detected.")
    if missing_from_registry:
        print(f"- Packages present in requirements but missing from registry: {', '.join(missing_from_registry[:10])}")
    if extra_in_markdown:
        print(f"- Packages present in markdown but missing from registry: {', '.join(extra_in_markdown[:10])}")
    if extra_in_ui:
        print(f"- Packages present in UI docs but missing from registry: {', '.join(extra_in_ui[:10])}")
    if extra_projects_in_markdown:
        print(f"- Projects present in markdown but missing from registry: {', '.join(extra_projects_in_markdown[:10])}")
    if extra_projects_in_ui:
        print(f"- Projects present in UI docs but missing from registry: {', '.join(extra_projects_in_ui[:10])}")
    if extra_languages_in_markdown:
        print(
            "- Languages/frameworks present in markdown but missing from registry: "
            f"{', '.join(extra_languages_in_markdown[:10])}"
        )
    if extra_languages_in_ui:
        print(
            "- Languages/frameworks present in UI docs but missing from registry: "
            f"{', '.join(extra_languages_in_ui[:10])}"
        )
    if drift_issues:
        print("- Drift issues (first 20):")
        for issue in drift_issues[:20]:
            print(f"  {issue}")
    if project_drift_issues:
        print("- Project drift issues (first 20):")
        for issue in project_drift_issues[:20]:
            print(f"  {issue}")
    if language_drift_issues:
        print("- Languages/frameworks drift issues (first 20):")
        for issue in language_drift_issues[:20]:
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