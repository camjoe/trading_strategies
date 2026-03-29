from __future__ import annotations

import argparse
from pathlib import Path

from common.repo_paths import get_repo_root
from scripts.documentation_ui.common.io import load_json
from scripts.documentation_ui.api.registry import parse_markdown, parse_routes, parse_ui_endpoints


def _endpoint_key(item: dict[str, str]) -> str:
    return f"{item['method']} {item['path']}"


def run_api_reference_check(repo_root: Path, registry_rel_path: str = "docs/reference/api.json") -> int:
    registry_path = repo_root / registry_rel_path
    if not registry_path.exists():
        print(f"ERROR: registry not found: {registry_path}")
        return 2

    existing = load_json(registry_path)
    endpoints = existing.get("endpoints", [])
    registry_by_key = {
        _endpoint_key(item): item
        for item in endpoints
        if isinstance(item.get("method"), str) and isinstance(item.get("path"), str)
    }

    code_routes = parse_routes(repo_root / "paper_trading_ui/backend/routes")
    markdown_routes = parse_markdown(repo_root / "docs/reference/API.md")
    ui_routes = parse_ui_endpoints(repo_root / "paper_trading_ui/frontend/src/views/docs.html")

    registry_keys = set(registry_by_key)
    code_keys = set(code_routes)
    markdown_keys = set(markdown_routes)
    ui_keys = set(ui_routes)

    missing_from_registry = sorted(code_keys - registry_keys)
    drift_issues: list[str] = []

    for key in sorted(registry_keys):
        item = registry_by_key[key]
        code_item = code_routes.get(key)
        markdown_item = markdown_routes.get(key)
        ui_item = ui_routes.get(key)
        if code_item is None:
            drift_issues.append(f"- {key}: present in registry but missing from FastAPI routes")
            continue
        if item.get("handler") != code_item.get("handler"):
            drift_issues.append(f"- {key}: registry handler differs from code")
        if item.get("module") != code_item.get("module"):
            drift_issues.append(f"- {key}: registry module differs from code")
        if item.get("group") != code_item.get("group"):
            drift_issues.append(f"- {key}: registry group differs from inferred route group")
        if not str(item.get("description") or "").strip():
            drift_issues.append(f"- {key}: missing description")

        if markdown_item is None:
            drift_issues.append(f"- {key}: missing from API.md")
        else:
            if markdown_item.get("handler") != item.get("handler"):
                drift_issues.append(f"- {key}: markdown handler differs from registry")
            if markdown_item.get("description") != item.get("description"):
                drift_issues.append(f"- {key}: markdown description differs from registry")
            if markdown_item.get("group") != item.get("group"):
                drift_issues.append(f"- {key}: markdown group differs from registry")

        if ui_item is None:
            drift_issues.append(f"- {key}: missing from docs.html API section")
        else:
            if ui_item.get("description") != item.get("description"):
                drift_issues.append(f"- {key}: UI description differs from registry")
            if ui_item.get("group") != item.get("group"):
                drift_issues.append(f"- {key}: UI group differs from registry")

    extra_in_markdown = sorted(markdown_keys - registry_keys)
    extra_in_ui = sorted(ui_keys - registry_keys)

    print("API Reference Check")
    print(f"Repo root: {repo_root}")
    print(f"Registry: {registry_path}")
    print(f"Endpoints in registry: {len(registry_by_key)}")
    print(f"FastAPI routes parsed: {len(code_keys)}")
    print(f"Markdown endpoints parsed: {len(markdown_keys)}")
    print(f"UI endpoints parsed: {len(ui_keys)}")

    if not missing_from_registry and not extra_in_markdown and not extra_in_ui and not drift_issues:
        print("\nPASS: API reference is in sync with code, markdown, and UI docs.")
        return 0

    print("\nFAIL: API reference drift detected.")
    if missing_from_registry:
        print(f"- Endpoints present in code but missing from registry: {', '.join(missing_from_registry[:10])}")
    if extra_in_markdown:
        print(f"- Endpoints present in markdown but missing from registry: {', '.join(extra_in_markdown[:10])}")
    if extra_in_ui:
        print(f"- Endpoints present in UI docs but missing from registry: {', '.join(extra_in_ui[:10])}")
    if drift_issues:
        print("- Drift issues (first 20):")
        for issue in drift_issues[:20]:
            print(f"  {issue}")

    print("\nUpdate the registry and/or source docs, then re-run checks.")
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate docs/reference/api.json against code, markdown, and UI docs.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    parser.add_argument("--registry", default="docs/reference/api.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_api_reference_check(repo_root=repo_root, registry_rel_path=args.registry)


if __name__ == "__main__":
    raise SystemExit(main())