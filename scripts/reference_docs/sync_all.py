from __future__ import annotations

import argparse
import json
from pathlib import Path

from common.repo_paths import get_repo_root
from scripts.documentation_ui.api.registry import render_markdown as render_api_markdown
from scripts.documentation_ui.api.sync_ui_docs import load_registry as load_api_registry
from scripts.documentation_ui.api.sync_ui_docs import rewrite_api_card
from scripts.documentation_ui.software.registry import render_markdown as render_software_markdown
from scripts.documentation_ui.software.sync_ui_docs import load_registry as load_software_registry
from scripts.documentation_ui.software.sync_ui_docs import rewrite_software_card
from scripts.documentation_ui.finance.sync_glossary import load_registry_overrides, rewrite_glossary
from scripts.documentation_ui.finance.sync_ui_docs import load_registry as load_terms_registry
from scripts.documentation_ui.finance.sync_ui_docs import rewrite_financial_card


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync all documentation-page reference surfaces from their canonical registries.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    return parser.parse_args()


def _sync_terms(repo_root: Path) -> None:
    registry_path = repo_root / "docs/reference/finance.json"
    finance_path = repo_root / "docs/reference/Finance.md"
    ui_docs_path = repo_root / "paper_trading_ui/frontend/src/views/docs.html"

    overrides = load_registry_overrides(registry_path)
    matched, updated = rewrite_glossary(finance_path, overrides)
    print(f"Finance rows matched: {matched}")
    print(f"Finance definitions updated: {updated}")

    terms = load_terms_registry(registry_path)
    original_html = ui_docs_path.read_text(encoding="utf-8")
    rewritten_html, changed_sections = rewrite_financial_card(original_html, terms)
    ui_docs_path.write_text(rewritten_html, encoding="utf-8")
    print(f"Financial & Market UI sections rewritten: {changed_sections}")


def _sync_software(repo_root: Path) -> None:
    registry_path = repo_root / "docs/reference/software.json"
    markdown_path = repo_root / "docs/reference/Software.md"
    ui_docs_path = repo_root / "paper_trading_ui/frontend/src/views/docs.html"

    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    markdown_path.write_text(render_software_markdown(payload.get("packages", [])), encoding="utf-8")
    print(f"Updated file: {markdown_path}")

    packages = load_software_registry(registry_path)
    original_html = ui_docs_path.read_text(encoding="utf-8")
    rewritten_html, replacement_count = rewrite_software_card(original_html, packages)
    ui_docs_path.write_text(rewritten_html, encoding="utf-8")
    print(f"Software UI sections rewritten: {replacement_count}")


def _sync_api(repo_root: Path) -> None:
    registry_path = repo_root / "docs/reference/api.json"
    markdown_path = repo_root / "docs/reference/API.md"
    ui_docs_path = repo_root / "paper_trading_ui/frontend/src/views/docs.html"

    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    markdown_path.write_text(render_api_markdown(payload.get("endpoints", [])), encoding="utf-8")
    print(f"Updated file: {markdown_path}")

    endpoints = load_api_registry(registry_path)
    original_html = ui_docs_path.read_text(encoding="utf-8")
    rewritten_html, changed_sections = rewrite_api_card(original_html, endpoints)
    ui_docs_path.write_text(rewritten_html, encoding="utf-8")
    print(f"API UI sections rewritten: {changed_sections}")


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    _sync_terms(repo_root)
    _sync_software(repo_root)
    _sync_api(repo_root)
    print("\nReference documentation sync completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())