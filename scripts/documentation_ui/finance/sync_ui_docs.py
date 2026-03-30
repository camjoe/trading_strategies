from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from scripts.documentation_ui.common.html import find_card_bounds, strip_html as _strip_html
from scripts.documentation_ui.common.io import load_json


SECTION_BLOCK_RE = re.compile(
    r'(<div class="ref-section">\s*<h3>(?P<title>.*?)</h3>.*?<tbody>)(?P<body>.*?)(</tbody>)(?P<tail>.*?</div>)',
    re.DOTALL,
)
ROW_TERM_RE = re.compile(r"<tr>\s*<td>(.*?)</td>", re.DOTALL)

UI_TERM_LABELS = {
    "DTE": "DTE (Days to Expiration)",
}


def strip_html(value: str) -> str:
    return _strip_html(value, remove_comments=True)


def load_registry(path: Path) -> list[dict[str, str]]:
    data = load_json(path)
    return [item for item in data.get("terms", []) if isinstance(item.get("term"), str)]


def infer_ui_section(term: dict[str, str]) -> str | None:
    group = term.get("group")
    if group == "Execution and Risk Controls":
        return "Execution & Risk Controls"
    if group == "Performance and Risk":
        return "Performance & Benchmarking"
    if group == "Options and Volatility":
        return "Options / Derivatives"
    if group == "Backtesting and Validation":
        return "Data & Backtesting Integrity"
    if group == "Technical Analysis":
        return "Technical Signals"
    if group == "Trading Strategies":
        return "Trading Strategies"
    if group in {"Areas of Focus", "Asset Classes"}:
        return "Asset Classes"
    return None


def parse_existing_order(financial_body: str) -> dict[str, list[str]]:
    order: dict[str, list[str]] = {}
    for match in SECTION_BLOCK_RE.finditer(financial_body):
        title = strip_html(match.group("title"))
        body = match.group("body")
        terms = [strip_html(term_match.group(1)) for term_match in ROW_TERM_RE.finditer(body)]
        order[title] = [term for term in terms if term]
    return order


def sort_terms_for_section(terms: list[dict[str, str]], existing_order: list[str]) -> list[dict[str, str]]:
    position = {name: index for index, name in enumerate(existing_order)}
    known: list[dict[str, str]] = []
    unknown: list[dict[str, str]] = []
    for term in terms:
        label = UI_TERM_LABELS.get(term["term"], term["term"])
        if label in position:
            known.append(term)
        else:
            unknown.append(term)

    known.sort(key=lambda item: position[UI_TERM_LABELS.get(item["term"], item["term"])])
    unknown.sort(key=lambda item: item["term"].lower())
    return known + unknown


def render_rows(terms: list[dict[str, str]]) -> str:
    if not terms:
        return ""
    lines = []
    for term in terms:
        label = UI_TERM_LABELS.get(term["term"], term["term"])
        definition = term["definition"]
        lines.append(
            f"          <tr><td>{html.escape(label, quote=False)}</td>"
            f"<td>{html.escape(definition, quote=False)}</td></tr>"
        )
    return "\n" + "\n".join(lines) + "\n        "


def build_ui_section_terms(registry_terms: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    section_terms = {
        "Performance & Benchmarking": [],
        "Execution & Risk Controls": [],
        "Options / Derivatives": [],
        "Data & Backtesting Integrity": [],
        "Technical Signals": [],
        "Trading Strategies": [],
        "Asset Classes": [],
    }
    for term in registry_terms:
        use = term.get("use")
        if use not in {"both", "ui"}:
            continue
        section = infer_ui_section(term)
        if section is None:
            continue
        section_terms[section].append(term)
    return section_terms


def find_financial_card_bounds(html_text: str) -> tuple[int, int]:
    return find_card_bounds(
        html_text,
        "<h2>Financial &amp; Market Knowledge</h2>",
        end_at_next_card=True,
    )


def rewrite_financial_card(html_text: str, registry_terms: list[dict[str, str]]) -> tuple[str, int]:
    start_index, end_index = find_financial_card_bounds(html_text)
    financial_card = html_text[start_index:end_index]

    existing_order = parse_existing_order(financial_card)
    ui_section_terms = build_ui_section_terms(registry_terms)
    changed_sections = 0

    def replace_section(match: re.Match[str]) -> str:
        nonlocal changed_sections
        title = strip_html(match.group("title"))
        if title not in ui_section_terms:
            return match.group(0)
        sorted_terms = sort_terms_for_section(ui_section_terms[title], existing_order.get(title, []))
        new_body = render_rows(sorted_terms)
        if new_body != match.group("body"):
            changed_sections += 1
        return f"{match.group(1)}{new_body}{match.group(4)}{match.group('tail')}"

    rewritten_card = SECTION_BLOCK_RE.sub(replace_section, financial_card)
    updated_html = html_text[:start_index] + rewritten_card + html_text[end_index:]
    return updated_html, changed_sections


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sync Financial & Market Knowledge tables in paper_trading_ui/frontend/src/views/docs.html "
            "from docs/reference/finance.json."
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
        "--ui-docs",
        type=Path,
        default=Path("paper_trading_ui/frontend/src/views/docs.html"),
        help="UI docs HTML path relative to repo root unless absolute.",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    registry_path = args.registry if args.registry.is_absolute() else repo_root / args.registry
    ui_docs_path = args.ui_docs if args.ui_docs.is_absolute() else repo_root / args.ui_docs

    registry_terms = load_registry(registry_path)
    original_html = ui_docs_path.read_text(encoding="utf-8")
    rewritten_html, changed_sections = rewrite_financial_card(original_html, registry_terms)
    ui_docs_path.write_text(rewritten_html, encoding="utf-8")

    print(f"Updated file: {ui_docs_path}")
    print(f"Sections rewritten: {changed_sections}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())