from __future__ import annotations

import argparse
import json
from pathlib import Path

from common.repo_paths import get_repo_root
from scripts.terms.registry import parse_glossary, parse_ui_terms


def _load_registry(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_term_definitions_check(repo_root: Path, registry_rel_path: str = "docs/reference/term_definitions.json") -> int:
    registry_path = repo_root / registry_rel_path
    if not registry_path.exists():
        print(f"ERROR: registry not found: {registry_path}")
        return 2

    existing = _load_registry(registry_path)
    existing_terms = existing.get("terms", [])
    existing_by_term = {
        term.get("term"): term for term in existing_terms if isinstance(term.get("term"), str)
    }

    glossary_terms = parse_glossary(repo_root / "docs/reference/Glossary.md")
    ui_terms = parse_ui_terms(repo_root / "paper_trading_ui/frontend/src/views/docs.html")
    registry_terms = set(existing_by_term)
    glossary_term_names = set(glossary_terms)
    ui_term_names = set(ui_terms)

    missing_from_registry = sorted((glossary_term_names | ui_term_names) - registry_terms)
    drift_issues: list[str] = []

    for term_name in sorted(registry_terms):
        item = existing_by_term[term_name]
        use = item.get("use")
        definition = item.get("definition")
        group = item.get("group")

        if use not in {"both", "glossary", "ui"}:
            drift_issues.append(f"- {term_name}: invalid use '{use}'")
            continue
        if not isinstance(definition, str) or not definition.strip():
            drift_issues.append(f"- {term_name}: missing definition")
            continue

        glossary_entry = glossary_terms.get(term_name)
        ui_entry = ui_terms.get(term_name)

        if use in {"both", "glossary"}:
            if glossary_entry is None:
                drift_issues.append(f"- {term_name}: missing from Glossary")
            else:
                if glossary_entry[1] != definition:
                    drift_issues.append(f"- {term_name}: Glossary definition differs from registry")
                if glossary_entry[0] != group:
                    drift_issues.append(f"- {term_name}: Glossary section differs from registry group")
        elif glossary_entry is not None:
            drift_issues.append(f"- {term_name}: unexpectedly present in Glossary")

        if use in {"both", "ui"}:
            if ui_entry is None:
                drift_issues.append(f"- {term_name}: missing from UI docs")
            else:
                if ui_entry[1] != definition:
                    drift_issues.append(f"- {term_name}: UI definition differs from registry")
        elif ui_entry is not None:
            drift_issues.append(f"- {term_name}: unexpectedly present in UI docs")

    extra_in_glossary = sorted(glossary_term_names - registry_terms)
    extra_in_ui = sorted(ui_term_names - registry_terms)

    print("Term Definition Registry Check")
    print(f"Repo root: {repo_root}")
    print(f"Registry: {registry_path}")
    print(f"Terms in registry: {len(existing_by_term)}")
    print(f"Glossary terms parsed: {len(glossary_term_names)}")
    print(f"UI terms parsed: {len(ui_term_names)}")

    if not missing_from_registry and not extra_in_glossary and not extra_in_ui and not drift_issues:
        print("\nPASS: term registry is in sync with Glossary/UI source docs.")
        return 0

    print("\nFAIL: term registry drift detected.")
    if missing_from_registry:
        print(f"- Terms present in docs but missing from registry: {', '.join(missing_from_registry[:10])}")
    if extra_in_glossary:
        print(f"- Terms present in Glossary but missing from registry: {', '.join(extra_in_glossary[:10])}")
    if extra_in_ui:
        print(f"- Terms present in UI docs but missing from registry: {', '.join(extra_in_ui[:10])}")
    if drift_issues:
        print("- Drift issues (first 20):")
        for diff in drift_issues[:20]:
            print(f"  {diff}")

    print("\nUpdate the registry and/or source docs, then re-run checks.")
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate docs/reference/term_definitions.json is synchronized with Glossary and UI docs.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to detected workspace root.",
    )
    parser.add_argument(
        "--registry",
        default="docs/reference/term_definitions.json",
        help="Registry path relative to repo root.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_term_definitions_check(repo_root=repo_root, registry_rel_path=args.registry)


if __name__ == "__main__":
    raise SystemExit(main())