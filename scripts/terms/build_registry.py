from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.terms.registry import build_registry, load_existing_state, parse_glossary, parse_ui_terms


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build canonical term registry from docs/reference/Glossary.md and "
            "paper_trading_ui/frontend/src/views/docs.html."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root path (default: inferred from this script location).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("docs/reference/term_definitions.json"),
        help="Output registry path relative to repo root unless absolute.",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    out_path = args.out if args.out.is_absolute() else repo_root / args.out
    glossary_path = repo_root / "docs/reference/Glossary.md"
    ui_docs_path = repo_root / "paper_trading_ui/frontend/src/views/docs.html"

    glossary_terms = parse_glossary(glossary_path)
    ui_terms = parse_ui_terms(ui_docs_path)
    existing_state, uses_surface_semantics = load_existing_state(out_path)

    rows = build_registry(glossary_terms, ui_terms, existing_state, uses_surface_semantics)

    output = {
        "schema_version": 2,
        "use_semantics": "surfaces",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "sources": {
            "glossary": str(glossary_path.relative_to(repo_root)).replace("\\", "/"),
            "ui_docs": str(ui_docs_path.relative_to(repo_root)).replace("\\", "/"),
        },
        "instructions": (
            "Edit use to 'both', 'glossary', or 'ui' and edit definition as needed, then re-run this script."
        ),
        "editing_notes": [
            "Terms using both surfaces appear first, then glossary-only, then ui-only.",
            "Group is the display section, preferring Glossary section when present.",
            "Use controls whether the definition should exist in both docs, only Glossary, or only the UI docs page.",
        ],
        "terms": rows,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    both = sum(1 for row in rows if row["use"] == "both")
    glossary_only = sum(1 for row in rows if row["use"] == "glossary")
    ui_only = sum(1 for row in rows if row["use"] == "ui")

    print(f"Wrote term registry: {out_path}")
    print(f"  Total terms: {len(rows)}")
    print(f"  Shared terms: {both}")
    print(f"  Glossary only: {glossary_only}")
    print(f"  UI only: {ui_only}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())