from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from scripts.documentation_ui.finance.registry import normalize_term


TABLE_ROW_RE = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")


def load_registry_overrides(registry_path: Path) -> dict[str, str]:
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    overrides: dict[str, str] = {}
    for item in data.get("terms", []):
        term = item.get("term")
        use = item.get("use")
        definition = item.get("definition")
        if not isinstance(term, str):
            continue
        if use in {"both", "glossary"} and isinstance(definition, str):
            overrides[normalize_term(term)] = definition
    return overrides


def rewrite_glossary(glossary_path: Path, overrides: dict[str, str]) -> tuple[int, int]:
    lines = glossary_path.read_text(encoding="utf-8").splitlines()
    out_lines: list[str] = []
    updated = 0
    matched = 0

    for line in lines:
        match = TABLE_ROW_RE.match(line)
        if not match:
            out_lines.append(line)
            continue

        term_raw = match.group(1).strip()
        definition_raw = match.group(2).strip()
        if term_raw.lower() in {"term", "concept", "asset class"}:
            out_lines.append(line)
            continue
        if set(term_raw) == {"-"} or set(definition_raw) == {"-"}:
            out_lines.append(line)
            continue

        normalized_term = normalize_term(term_raw)
        replacement = overrides.get(normalized_term)
        if replacement is None:
            out_lines.append(line)
            continue

        matched += 1
        if definition_raw != replacement:
            updated += 1
            out_lines.append(f"| {term_raw} | {replacement} |")
        else:
            out_lines.append(line)

    glossary_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return matched, updated


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sync docs/reference/Finance.md definitions from canonical values in "
            "docs/reference/finance.json for terms whose use includes glossary."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[3],
        help="Repository root path (default: inferred from this script location).",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("docs/reference/finance.json"),
        help="Registry path relative to repo root unless absolute.",
    )
    parser.add_argument(
        "--glossary",
        type=Path,
        default=Path("docs/reference/Finance.md"),
        help="Finance path relative to repo root unless absolute.",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    registry_path = args.registry if args.registry.is_absolute() else repo_root / args.registry
    glossary_path = args.glossary if args.glossary.is_absolute() else repo_root / args.glossary

    overrides = load_registry_overrides(registry_path)
    matched, updated = rewrite_glossary(glossary_path, overrides)

    print(f"Registry terms applied to finance rows: {matched}")
    print(f"Finance definitions updated from registry: {updated}")
    print(f"Updated file: {glossary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())