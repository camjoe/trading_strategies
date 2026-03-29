from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

from common.repo_paths import get_repo_root
from scripts.documentation_ui.api.registry import GROUP_ORDER


SECTION_BLOCK_RE = re.compile(
    r'(<div class="ref-section">\s*<h3>(?P<title>.*?)</h3>.*?<tbody>)(?P<body>.*?)(</tbody>)(?P<tail>.*?</div>)',
    re.DOTALL,
)
HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(value: str) -> str:
    text = html.unescape(value)
    text = HTML_TAG_RE.sub("", text)
    return " ".join(text.split()).strip()


def load_registry(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [item for item in payload.get("endpoints", []) if isinstance(item.get("path"), str)]


def find_api_card_bounds(html_text: str) -> tuple[int, int]:
    heading = "<h2>API Reference</h2>"
    heading_index = html_text.find(heading)
    if heading_index == -1:
        raise ValueError("Could not locate API Reference heading in docs.html")

    start_index = html_text.rfind('<section class="card ref-card">', 0, heading_index)
    if start_index == -1:
        raise ValueError("Could not locate start of API Reference card")

    return start_index, len(html_text)


def build_grouped_endpoints(endpoints: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped = {group: [] for group in GROUP_ORDER}
    for endpoint in endpoints:
        group = str(endpoint.get("group") or "")
        if group not in grouped:
            continue
        grouped[group].append(endpoint)
    for group in grouped:
        grouped[group].sort(key=lambda item: (str(item["path"]), str(item["method"])))
    return grouped


def render_rows(endpoints: list[dict[str, str]]) -> str:
    if not endpoints:
        return ""
    lines = []
    for endpoint in endpoints:
        method_path = f"{endpoint['method']} {endpoint['path']}"
        lines.append(
            f"          <tr><td>{html.escape(method_path, quote=False)}</td>"
            f"<td>{html.escape(str(endpoint['description']), quote=False)}</td></tr>"
        )
    return "\n" + "\n".join(lines) + "\n        "


def rewrite_api_card(html_text: str, endpoints: list[dict[str, str]]) -> tuple[str, int]:
    start_index, end_index = find_api_card_bounds(html_text)
    api_card = html_text[start_index:end_index]
    grouped = build_grouped_endpoints(endpoints)
    changed_sections = 0

    def replace_section(match: re.Match[str]) -> str:
        nonlocal changed_sections
        title = strip_html(match.group("title"))
        if title not in grouped:
            return match.group(0)
        new_body = render_rows(grouped[title])
        if new_body != match.group("body"):
            changed_sections += 1
        return f"{match.group(1)}{new_body}{match.group(4)}{match.group('tail')}"

    rewritten_card = SECTION_BLOCK_RE.sub(replace_section, api_card)
    return html_text[:start_index] + rewritten_card + html_text[end_index:], changed_sections


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync the API endpoint tables in docs.html from docs/reference/api.json.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    parser.add_argument("--registry", default="docs/reference/api.json")
    parser.add_argument("--ui-docs", default="paper_trading_ui/frontend/src/views/docs.html")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    registry_path = repo_root / args.registry
    ui_docs_path = repo_root / args.ui_docs
    endpoints = load_registry(registry_path)
    original_html = ui_docs_path.read_text(encoding="utf-8")
    rewritten_html, changed_sections = rewrite_api_card(original_html, endpoints)
    ui_docs_path.write_text(rewritten_html, encoding="utf-8")
    print(f"Updated file: {ui_docs_path}")
    print(f"Sections rewritten: {changed_sections}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())