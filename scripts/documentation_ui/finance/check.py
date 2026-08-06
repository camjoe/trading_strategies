from __future__ import annotations

import argparse
import json
from pathlib import Path

from common.git import get_repo_root
from scripts.documentation_ui.finance.registry import (
    FINANCE_DOC_REL,
    FINANCE_REGISTRY_REL,
    build_payload,
    parse_finance_reference,
)


def run_finance_reference_check(
    repo_root: Path,
    registry_rel_path: str = FINANCE_REGISTRY_REL,
    doc_rel_path: str = FINANCE_DOC_REL,
) -> int:
    registry_path = repo_root / registry_rel_path
    doc_path = repo_root / doc_rel_path
    if not doc_path.exists():
        print(f"ERROR: finance reference doc not found: {doc_path}")
        return 2
    if not registry_path.exists():
        print(f"ERROR: finance registry not found: {registry_path}")
        return 2

    expected = build_payload(parse_finance_reference(doc_path))
    existing = json.loads(registry_path.read_text(encoding="utf-8"))

    print("Finance Reference Check")
    print(f"Source: {doc_path.relative_to(repo_root)}")
    print(f"Registry: {registry_path.relative_to(repo_root)}")
    print(f"Terms in source: {len(expected['terms'])}")
    print(f"Terms in registry: {len(existing.get('terms', []))}")

    if existing == expected:
        print("\nPASS: finance registry is in sync with the reference doc.")
        return 0

    print("\nFAIL: finance registry drift detected.")
    print("  Run: python -m scripts.documentation_ui.sync")
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that assets/finance.json is in sync with docs/reference/financial-market-knowledge.md.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = get_repo_root(__file__) if args.repo_root is None else Path(args.repo_root).resolve()
    return run_finance_reference_check(repo_root=repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
