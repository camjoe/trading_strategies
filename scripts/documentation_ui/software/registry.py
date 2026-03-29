from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.documentation_ui.common.html import extract_card_body, strip_html


GROUP_ORDER = [
    "Data & Market Access",
    "Analysis & Modeling",
    "Visualization",
    "Backend & Validation",
    "Developer Tooling",
]

GROUP_BY_PACKAGE = {
    "fastapi": "Backend & Validation",
    "httpx": "Developer Tooling",
    "hypothesis": "Developer Tooling",
    "matplotlib": "Visualization",
    "numpy": "Analysis & Modeling",
    "pandas": "Analysis & Modeling",
    "pydantic": "Backend & Validation",
    "pytest": "Developer Tooling",
    "pytest-cov": "Developer Tooling",
    "pytest-mock": "Developer Tooling",
    "python-dotenv": "Backend & Validation",
    "uvicorn": "Backend & Validation",
    "yfinance": "Data & Market Access",
}

SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")
TABLE_ROW_RE = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")
SOFTWARE_SECTION_RE = re.compile(
    r'<div class="ref-section">\s*<h3>Key Python Packages</h3>(?P<body>.*?)</div>',
    re.DOTALL,
)
UI_GROUP_RE = re.compile(
    r'<p class="ref-subsection-label">(?P<title>.*?)</p>\s*'
    r'<table class="ref-table ref-table--software">\s*<thead>.*?</thead>\s*<tbody>(?P<body>.*?)</tbody>\s*</table>',
    re.DOTALL,
)
UI_ROW_RE = re.compile(r"<tr>\s*(?P<cells>.*?)\s*</tr>", re.DOTALL)
UI_CELL_RE = re.compile(r"<td>(.*?)</td>", re.DOTALL)


def normalize_package_name(raw: str) -> str:
    cleaned = " ".join(raw.split()).strip()
    base = cleaned.split("[", 1)[0]
    return base.lower()


def parse_requirement_entry(raw: str) -> tuple[str, str] | None:
    line = raw.strip()
    if not line or line.startswith("#") or line.startswith("-r"):
        return None

    for marker in ("==", ">=", "<=", "~=", "!=", ">", "<"):
        if marker in line:
            name, remainder = line.split(marker, 1)
            return name.strip(), f"{marker}{remainder.strip()}"
    return line, ""


def parse_requirements_file(path: Path, scope: str) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = parse_requirement_entry(line)
        if parsed is None:
            continue
        display_name, version = parsed
        key = normalize_package_name(display_name)
        rows[key] = {
            "name": display_name,
            "version": version,
            "scope": scope,
        }
    return rows


def parse_requirements(base_path: Path, dev_path: Path) -> dict[str, dict[str, str]]:
    rows = parse_requirements_file(base_path, scope="runtime")
    for key, value in parse_requirements_file(dev_path, scope="development").items():
        if key not in rows:
            rows[key] = value
    return rows


def load_existing_state(registry_path: Path) -> dict[str, dict[str, str]]:
    if not registry_path.exists():
        return {}
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    rows: dict[str, dict[str, str]] = {}
    for item in payload.get("packages", []):
        name = item.get("name")
        if not isinstance(name, str):
            continue
        rows[normalize_package_name(name)] = {
            "group": str(item.get("group") or ""),
            "purpose": str(item.get("purpose") or ""),
        }
    return rows


def build_registry(
    parsed_requirements: dict[str, dict[str, str]],
    existing_state: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key in sorted(parsed_requirements, key=str.lower):
        package = parsed_requirements[key]
        existing = existing_state.get(key, {})
        group = existing.get("group") or GROUP_BY_PACKAGE.get(key, "Backend & Validation")
        purpose = existing.get("purpose") or ""
        group_rank = GROUP_ORDER.index(group) if group in GROUP_ORDER else len(GROUP_ORDER)
        rows.append(
            {
                "name": package["name"],
                "version": package["version"],
                "scope": package["scope"],
                "group": group,
                "purpose": purpose,
                "_sort_group": str(group_rank),
            }
        )

    rows.sort(key=lambda item: (int(item["_sort_group"]), item["name"].lower()))
    for row in rows:
        del row["_sort_group"]
    return rows


def render_markdown(packages: list[dict[str, str]]) -> str:
    lines = [
        "# Software Reference",
        "",
        "Canonical software package inventory for the Software section of the documentation page.",
        "",
    ]

    grouped: dict[str, list[dict[str, str]]] = {}
    for package in packages:
        grouped.setdefault(package["group"], []).append(package)

    ordered_groups = [group for group in GROUP_ORDER if group in grouped]
    ordered_groups.extend(sorted(group for group in grouped if group not in GROUP_ORDER))

    for group in ordered_groups:
        lines.extend(
            [
                f"## {group}",
                "",
                "| Package | Version | Scope | Purpose |",
                "| --- | --- | --- | --- |",
            ]
        )
        for package in grouped[group]:
            lines.append(
                f"| {package['name']} | {package['version'] or '-'} | {package['scope']} | {package['purpose']} |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def parse_markdown(markdown_path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    current_group = ""
    for line in markdown_path.read_text(encoding="utf-8").splitlines():
        section_match = SECTION_RE.match(line)
        if section_match:
            current_group = section_match.group(1).strip()
            continue

        row_match = TABLE_ROW_RE.match(line)
        if not row_match:
            continue

        name = row_match.group(1).strip()
        if name.lower() == "package" or set(name) == {"-"}:
            continue

        key = normalize_package_name(name)
        rows[key] = {
            "name": name,
            "version": row_match.group(2).strip(),
            "scope": row_match.group(3).strip(),
            "purpose": row_match.group(4).strip(),
            "group": current_group,
        }
    return rows


def extract_software_card_body(raw: str) -> str:
    return extract_card_body(raw, "<h2>Software</h2>", end_at_next_card=True)


def parse_ui_packages(ui_docs_path: Path) -> dict[str, dict[str, str]]:
    raw = ui_docs_path.read_text(encoding="utf-8")
    card_body = extract_software_card_body(raw)
    if not card_body:
        return {}

    section_match = SOFTWARE_SECTION_RE.search(card_body)
    if section_match is None:
        return {}

    rows: dict[str, dict[str, str]] = {}
    for group_match in UI_GROUP_RE.finditer(section_match.group("body")):
        group = strip_html(group_match.group("title"))
        for row_match in UI_ROW_RE.finditer(group_match.group("body")):
            raw_cells = UI_CELL_RE.findall(row_match.group("cells"))
            cells = [strip_html(value) for value in raw_cells]
            if len(cells) < 2:
                continue

            name = cells[0]
            if len(cells) >= 3:
                version = cells[1]
                purpose = cells[2]
            else:
                version = ""
                purpose = cells[1]

            key = normalize_package_name(name)
            rows[key] = {
                "name": name,
                "version": version,
                "purpose": purpose,
                "group": group,
            }
    return rows