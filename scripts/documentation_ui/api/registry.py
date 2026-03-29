from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from scripts.documentation_ui.common.html import extract_card_body, strip_html


GROUP_ORDER = [
    "Accounts & Snapshots Endpoints",
    "Admin Endpoints",
    "Logs Endpoints",
    "Backtesting Endpoints",
]

GROUP_BY_MODULE = {
    "accounts": "Accounts & Snapshots Endpoints",
    "actions": "Accounts & Snapshots Endpoints",
    "health": "Accounts & Snapshots Endpoints",
    "admin": "Admin Endpoints",
    "logs": "Logs Endpoints",
    "backtests": "Backtesting Endpoints",
}

SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")
TABLE_ROW_RE = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")
API_SECTION_RE = re.compile(
    r'<div class="ref-section">\s*<h3>(?P<title>.*?)</h3>.*?<tbody>(?P<body>.*?)</tbody>',
    re.DOTALL,
)
UI_ROW_RE = re.compile(r'<tr>\s*<td>(?P<method_path>.*?)</td>\s*<td>(?P<purpose>.*?)</td>\s*</tr>', re.DOTALL)


def endpoint_key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"


def _parse_route_decorator(decorator: ast.AST) -> tuple[str, str] | None:
    if not isinstance(decorator, ast.Call):
        return None
    if not isinstance(decorator.func, ast.Attribute):
        return None
    if not isinstance(decorator.func.value, ast.Name) or decorator.func.value.id != "router":
        return None
    method = decorator.func.attr.upper()
    if not decorator.args:
        return None
    first_arg = decorator.args[0]
    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
        return method, first_arg.value
    return None


def parse_routes(routes_dir: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for path in sorted(routes_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        module = path.stem
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                parsed = _parse_route_decorator(decorator)
                if parsed is None:
                    continue
                method, route_path = parsed
                key = endpoint_key(method, route_path)
                rows[key] = {
                    "method": method,
                    "path": route_path,
                    "handler": node.name,
                    "module": module,
                    "group": GROUP_BY_MODULE.get(module, "Accounts & Snapshots Endpoints"),
                }
    return rows


def load_existing_state(registry_path: Path) -> dict[str, dict[str, str]]:
    if not registry_path.exists():
        return {}
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    rows: dict[str, dict[str, str]] = {}
    for item in payload.get("endpoints", []):
        method = item.get("method")
        path = item.get("path")
        if not isinstance(method, str) or not isinstance(path, str):
            continue
        rows[endpoint_key(method, path)] = {
            "group": str(item.get("group") or ""),
            "description": str(item.get("description") or ""),
        }
    return rows


def build_registry(
    parsed_routes: dict[str, dict[str, str]],
    existing_state: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key in sorted(parsed_routes, key=str.lower):
        route = parsed_routes[key]
        existing = existing_state.get(key, {})
        group = existing.get("group") or route["group"]
        description = existing.get("description") or ""
        group_rank = GROUP_ORDER.index(group) if group in GROUP_ORDER else len(GROUP_ORDER)
        rows.append(
            {
                "method": route["method"],
                "path": route["path"],
                "handler": route["handler"],
                "module": route["module"],
                "group": group,
                "description": description,
                "_sort_group": str(group_rank),
            }
        )
    rows.sort(key=lambda item: (int(item["_sort_group"]), item["path"], item["method"]))
    for row in rows:
        del row["_sort_group"]
    return rows


def render_markdown(endpoints: list[dict[str, str]]) -> str:
    lines = [
        "# API",
        "",
        "Canonical endpoint inventory for the API Reference section of the documentation page.",
        "",
    ]
    grouped: dict[str, list[dict[str, str]]] = {}
    for endpoint in endpoints:
        grouped.setdefault(endpoint["group"], []).append(endpoint)

    ordered_groups = [group for group in GROUP_ORDER if group in grouped]
    ordered_groups.extend(sorted(group for group in grouped if group not in GROUP_ORDER))

    for group in ordered_groups:
        lines.extend(
            [
                f"## {group}",
                "",
                "| Method | Path | Handler | Purpose |",
                "| --- | --- | --- | --- |",
            ]
        )
        for endpoint in grouped[group]:
            lines.append(
                f"| {endpoint['method']} | {endpoint['path']} | {endpoint['handler']} | {endpoint['description']} |"
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
        method = row_match.group(1).strip()
        if method.lower() == "method" or set(method) == {"-"}:
            continue

        path = row_match.group(2).strip()
        rows[endpoint_key(method, path)] = {
            "method": method,
            "path": path,
            "handler": row_match.group(3).strip(),
            "description": row_match.group(4).strip(),
            "group": current_group,
        }
    return rows


def extract_api_card_body(raw: str) -> str:
    return extract_card_body(raw, "<h2>API Reference</h2>", end_at_next_card=False)


def parse_ui_endpoints(ui_docs_path: Path) -> dict[str, dict[str, str]]:
    raw = ui_docs_path.read_text(encoding="utf-8")
    card_body = extract_api_card_body(raw)
    if not card_body:
        return {}

    rows: dict[str, dict[str, str]] = {}
    for section_match in API_SECTION_RE.finditer(card_body):
        title = strip_html(section_match.group("title"))
        if title not in GROUP_ORDER:
            continue

        for row_match in UI_ROW_RE.finditer(section_match.group("body")):
            method_path = strip_html(row_match.group("method_path"))
            if " " not in method_path:
                continue
            method, path = method_path.split(" ", 1)
            key = endpoint_key(method, path)
            rows[key] = {
                "method": method,
                "path": path,
                "description": strip_html(row_match.group("purpose")),
                "group": title,
            }
    return rows