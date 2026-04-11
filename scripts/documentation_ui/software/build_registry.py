from __future__ import annotations

import argparse
import json
from pathlib import Path

from common.repo_paths import get_repo_root
from scripts.documentation_ui.software.registry import build_registry, load_existing_state, parse_requirements


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build paper_trading_ui/frontend/src/assets/software.json from requirements files.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    parser.add_argument("--registry", default="paper_trading_ui/frontend/src/assets/software.json")
    parser.add_argument("--base", default="requirements-base.txt")
    parser.add_argument("--dev", default="requirements-dev.txt")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    registry_path = repo_root / args.registry
    existing_payload: dict[str, object] = {}
    if registry_path.exists():
        try:
            existing_payload = json.loads(registry_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing_payload = {}
    parsed_requirements = parse_requirements(repo_root / args.base, repo_root / args.dev)
    existing_state = load_existing_state(registry_path)
    packages = build_registry(parsed_requirements, existing_state)
    projects = existing_payload.get("projects", [])
    if not isinstance(projects, list):
        projects = []
    languages_frameworks = existing_payload.get("languages_frameworks", [])
    if not isinstance(languages_frameworks, list):
        languages_frameworks = []
    payload = {
        "schema_version": 2,
        "packages": packages,
        "projects": projects,
        "languages_frameworks": languages_frameworks,
    }
    registry_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote software registry: {registry_path}")
    print(f"Packages: {len(packages)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())