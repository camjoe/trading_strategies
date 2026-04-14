from __future__ import annotations

import ast
import json
from pathlib import Path

from scripts.documentation_ui.registry_utils import sort_registry_rows


ROUTES_DIR = "paper_trading_ui/backend/routes"
API_REGISTRY_REL = "paper_trading_ui/frontend/src/assets/api.json"

GROUP_ORDER = [
    "Accounts & Snapshots Endpoints",
    "Admin Endpoints",
    "Logs Endpoints",
    "Backtesting Endpoints",
]

GROUP_BY_MODULE = {
    "accounts": "Accounts & Snapshots Endpoints",
    "actions": "Accounts & Snapshots Endpoints",
    "analysis": "Accounts & Snapshots Endpoints",
    "features": "Accounts & Snapshots Endpoints",
    "health": "Accounts & Snapshots Endpoints",
    "trades": "Accounts & Snapshots Endpoints",
    "admin": "Admin Endpoints",
    "logs": "Logs Endpoints",
    "backtests": "Backtesting Endpoints",
}



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
    sort_registry_rows(rows, lambda item: (item["path"], item["method"]))
    return rows
