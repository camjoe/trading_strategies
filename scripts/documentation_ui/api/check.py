from __future__ import annotations

import argparse
from pathlib import Path

from common.repo_paths import get_repo_root
from scripts.documentation_ui.common.io import load_json
from scripts.documentation_ui.api.registry import parse_routes


def _endpoint_key(item: dict[str, str]) -> str:
    return f"{item['method']} {item['path']}"


def run_api_reference_check(
    repo_root: Path,
    registry_rel_path: str = "paper_trading_ui/frontend/src/assets/api.json",
) -> int:
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

    registry_keys = set(registry_by_key)
    code_keys = set(code_routes)

    missing_from_registry = sorted(code_keys - registry_keys)
    drift_issues: list[str] = []

    for key in sorted(registry_keys):
        item = registry_by_key[key]
        code_item = code_routes.get(key)
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

    print("API Reference Check")
    print(f"Registry: {registry_path.relative_to(repo_root)}")
    print(f"Endpoints in registry: {len(registry_by_key)}")
    print(f"FastAPI routes parsed: {len(code_keys)}")

    if not missing_from_registry and not drift_issues:
        print("\nPASS: API registry is in sync with FastAPI routes.")
        return 0

    print("\nFAIL: API registry drift detected.")
    if missing_from_registry:
        print(f"- Routes in code but missing from registry: {', '.join(missing_from_registry)}")
        print("  Run: python -m scripts.reference_docs.sync_all")
    if drift_issues:
        print("- Drift issues:")
        for issue in drift_issues[:20]:
            print(f"  {issue}")
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that assets/api.json is in sync with FastAPI routes.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = get_repo_root(__file__) if args.repo_root is None else __import__("pathlib").Path(args.repo_root).resolve()
    return run_api_reference_check(repo_root=repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
