from __future__ import annotations

import argparse
import json
from pathlib import Path

from common.paths.repo_paths import get_repo_root
from scripts.documentation_ui.finance.registry import (
    FINANCE_DOC_REL,
    FINANCE_REGISTRY_REL,
    build_payload,
    parse_finance_reference,
)


def run_build(repo_root: Path) -> None:
    """Build the finance registry JSON from the canonical reference doc."""
    doc_path = repo_root / FINANCE_DOC_REL
    registry_path = repo_root / FINANCE_REGISTRY_REL
    terms = parse_finance_reference(doc_path)
    payload = build_payload(terms)
    registry_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote finance registry: {registry_path}")
    print(f"Terms: {len(terms)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build apps/paper_trading_web/frontend/src/assets/finance.json from docs/reference/financial-market-knowledge.md.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    run_build(repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
