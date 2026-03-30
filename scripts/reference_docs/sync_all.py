from __future__ import annotations

import argparse
import json
from pathlib import Path

from common.repo_paths import get_repo_root
from scripts.documentation_ui.api.registry import build_registry as build_api_registry
from scripts.documentation_ui.api.registry import load_existing_state as load_api_state
from scripts.documentation_ui.api.registry import parse_routes
from scripts.documentation_ui.software.registry import build_registry as build_software_registry
from scripts.documentation_ui.software.registry import load_existing_state as load_software_state
from scripts.documentation_ui.software.registry import parse_requirements


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync frontend/src/assets reference JSON files from live code and requirements.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    return parser.parse_args()


def _sync_api(repo_root: Path) -> None:
    registry_path = repo_root / "paper_trading_ui/frontend/src/assets/api.json"
    parsed_routes = parse_routes(repo_root / "paper_trading_ui/backend/routes")
    existing_state = load_api_state(registry_path)
    endpoints = build_api_registry(parsed_routes, existing_state)
    try:
        api_basics = json.loads(registry_path.read_text(encoding="utf-8")).get("api_basics", [])
    except Exception:
        api_basics = []
    payload = {"schema_version": 1, "api_basics": api_basics, "endpoints": endpoints}
    registry_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"API: wrote {len(endpoints)} endpoints → {registry_path.relative_to(repo_root)}")


def _sync_software(repo_root: Path) -> None:
    registry_path = repo_root / "paper_trading_ui/frontend/src/assets/software.json"
    existing_payload: dict = {}
    if registry_path.exists():
        try:
            existing_payload = json.loads(registry_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    parsed_requirements = parse_requirements(
        repo_root / "requirements/base.txt",
        repo_root / "requirements/dev.txt",
    )
    existing_state = load_software_state(registry_path)
    packages = build_software_registry(parsed_requirements, existing_state)
    projects = existing_payload.get("projects", [])
    languages_frameworks = existing_payload.get("languages_frameworks", [])
    payload = {
        "schema_version": 2,
        "projects": projects,
        "languages_frameworks": languages_frameworks,
        "packages": packages,
    }
    registry_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Software: wrote {len(packages)} packages → {registry_path.relative_to(repo_root)}")


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    _sync_api(repo_root)
    _sync_software(repo_root)
    print("\nSync completed. finance.json is manually curated — edit it directly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())