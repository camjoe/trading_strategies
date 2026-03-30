from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Add repo root to sys.path for all imports
sys.path.insert(0, str((Path(__file__).resolve().parents[3])))
from common.repo_paths import get_repo_root
from scripts.documentation_ui.api.registry import render_markdown


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync docs/reference/API.md from docs/reference/api.json.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    parser.add_argument("--registry", default="docs/reference/api.json")
    parser.add_argument("--markdown", default="docs/reference/API.md")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    registry_path = repo_root / args.registry
    markdown_path = repo_root / args.markdown
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    endpoints = payload.get("endpoints", [])
    api_basics = payload.get("api_basics", [])
    content = render_markdown(endpoints, api_basics)
    markdown_path.write_text(content, encoding="utf-8")
    print(f"Updated file: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())