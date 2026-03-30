from __future__ import annotations

import argparse
import json
from pathlib import Path

from common.repo_paths import get_repo_root
from scripts.documentation_ui.api.registry import build_registry, load_existing_state, parse_routes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build paper_trading_ui/frontend/src/assets/api.json from FastAPI route modules.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    parser.add_argument("--registry", default="paper_trading_ui/frontend/src/assets/api.json")
    parser.add_argument("--routes-dir", default="paper_trading_ui/backend/routes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    registry_path = repo_root / args.registry
    parsed_routes = parse_routes(repo_root / args.routes_dir)
    existing_state = load_existing_state(registry_path)
    endpoints = build_registry(parsed_routes, existing_state)
    # Preserve api_basics if present in existing_state
    try:
        existing_payload = json.loads(registry_path.read_text(encoding="utf-8"))
        api_basics = existing_payload.get("api_basics", [])
    except Exception:
        api_basics = []
    payload = {
        "schema_version": 1,
        "api_basics": api_basics,
        "endpoints": endpoints,
    }
    registry_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote API registry: {registry_path}")
    print(f"Endpoints: {len(endpoints)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())