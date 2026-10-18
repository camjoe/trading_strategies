from __future__ import annotations

import argparse
import json
from pathlib import Path

from common.git import get_repo_root
from scripts.documentation_ui.commands.registry import COMMANDS_REGISTRY_REL, build_payload


def run_commands_reference_check(
    repo_root: Path,
    registry_rel_path: str = COMMANDS_REGISTRY_REL,
) -> int:
    registry_path = repo_root / registry_rel_path
    if not registry_path.exists():
        print(f"ERROR: registry not found: {registry_path}")
        return 2

    try:
        expected = build_payload()
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1
    existing = json.loads(registry_path.read_text(encoding="utf-8"))
    existing_names = {item.get("name") for item in existing.get("commands", [])}
    expected_names = {item["name"] for item in expected["commands"]}

    print("Command Reference Check")
    print(f"Registry: {registry_path.relative_to(repo_root)}")
    print(f"Commands in registry: {len(existing_names)}")
    print(f"CLI commands parsed: {len(expected_names)}")

    if existing == expected:
        print("\nPASS: command registry is in sync with the CLI parser.")
        return 0

    print("\nFAIL: command registry drift detected.")
    missing = sorted(expected_names - existing_names)
    extra = sorted(existing_names - expected_names)
    if missing:
        print(f"- Commands in code but missing from registry: {', '.join(missing)}")
    if extra:
        print(f"- Commands in registry but missing from code: {', '.join(extra)}")
    print("  Run: python -m scripts.documentation_ui.sync")
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that assets/commands.json is in sync with the CLI parser.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = get_repo_root(__file__) if args.repo_root is None else Path(args.repo_root).resolve()
    return run_commands_reference_check(repo_root=repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
