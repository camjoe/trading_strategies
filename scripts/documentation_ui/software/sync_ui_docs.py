from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from common.repo_paths import get_repo_root
from scripts.documentation_ui.common.html import find_card_bounds
from scripts.documentation_ui.common.io import load_json
from scripts.documentation_ui.software.registry import GROUP_ORDER


SOFTWARE_SECTION_RE = re.compile(
    r'(<div class="ref-section">\s*<h3>Key Python Packages</h3>)(?P<body>.*?)</div>',
    re.DOTALL,
)


def load_registry(path: Path) -> list[dict[str, str]]:
    payload = load_json(path)
    return [item for item in payload.get("packages", []) if isinstance(item.get("name"), str)]


def find_software_card_bounds(html_text: str) -> tuple[int, int]:
    return find_card_bounds(html_text, "<h2>Software</h2>", end_at_next_card=True)


def render_section_body(packages: list[dict[str, str]]) -> str:
    grouped: dict[str, list[dict[str, str]]] = {}
    for package in packages:
        grouped.setdefault(str(package.get("group") or "Backend & Validation"), []).append(package)

    ordered_groups = [group for group in GROUP_ORDER if group in grouped]
    ordered_groups.extend(sorted(group for group in grouped if group not in GROUP_ORDER))

    lines: list[str] = []
    for group in ordered_groups:
        lines.extend(
            [
                "",
                f"      <p class=\"ref-subsection-label\">{html.escape(group, quote=False)}</p>",
                '      <table class="ref-table ref-table--software">',
                '        <thead><tr><th>Package</th><th>Purpose</th></tr></thead>',
                "        <tbody>",
            ]
        )
        for package in grouped[group]:
            lines.append(
                f"          <tr><td>{html.escape(str(package['name']), quote=False)}</td>"
                f"<td>{html.escape(str(package['purpose']), quote=False)}</td></tr>"
            )
        lines.extend(["        </tbody>", "      </table>"])
    lines.append("    ")
    return "\n".join(lines)


def rewrite_software_card(html_text: str, packages: list[dict[str, str]]) -> tuple[str, int]:
    start_index, end_index = find_software_card_bounds(html_text)
    software_card = html_text[start_index:end_index]

    replacement_count = 0

    def replace_section(match: re.Match[str]) -> str:
        nonlocal replacement_count
        replacement_count += 1
        return f"{match.group(1)}{render_section_body(packages)}</div>"

    rewritten_card = SOFTWARE_SECTION_RE.sub(replace_section, software_card, count=1)
    return html_text[:start_index] + rewritten_card + html_text[end_index:], replacement_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync the Software section package tables in docs.html from software.json.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    parser.add_argument("--registry", default="docs/reference/software.json")
    parser.add_argument("--ui-docs", default="paper_trading_ui/frontend/src/views/docs.html")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    registry_path = repo_root / args.registry
    ui_docs_path = repo_root / args.ui_docs
    packages = load_registry(registry_path)
    original_html = ui_docs_path.read_text(encoding="utf-8")
    rewritten_html, replacement_count = rewrite_software_card(original_html, packages)
    ui_docs_path.write_text(rewritten_html, encoding="utf-8")
    print(f"Updated file: {ui_docs_path}")
    print(f"Sections rewritten: {replacement_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())