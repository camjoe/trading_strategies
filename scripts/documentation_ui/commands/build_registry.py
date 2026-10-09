from __future__ import annotations

import argparse
import json
from pathlib import Path

from common.git import get_repo_root
from scripts.documentation_ui.commands.registry import COMMANDS_REGISTRY_REL, build_payload


def run_build(repo_root: Path, registry_rel_path: str = COMMANDS_REGISTRY_REL) -> None:
    """Write the CLI command registry JSON from the live argparse parser."""
    registry_path = repo_root / registry_rel_path
    payload = build_payload()
    registry_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote command registry: {registry_path}")
    print(f"Commands: {len(payload['commands'])}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build apps/paper_trading_web/frontend/src/assets/commands.json from the CLI parser.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    parser.add_argument("--registry", default=COMMANDS_REGISTRY_REL)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    run_build(repo_root, args.registry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
