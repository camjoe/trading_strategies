from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from pydantic import BaseModel
import importlib.util
import sys


def extract_query_params_and_body_models(routes_dir: Path, schemas_path: Path) -> dict[str, dict[str, Any]]:
    """
    For each endpoint, extract query parameters and request body model fields.
    Returns a dict keyed by endpoint (e.g. 'GET /api/logs/{file_name}') with:
      - 'query_params': list of dicts with name, type, default, constraints, description
      - 'body_model': dict with model name and list of fields (name, type, default, description)
    """
    # Load schemas module for Pydantic model introspection
    spec = importlib.util.spec_from_file_location("schemas", schemas_path)
    schemas = importlib.util.module_from_spec(spec)
    sys.modules["schemas"] = schemas
    spec.loader.exec_module(schemas)

    endpoints = {}
    for path in sorted(routes_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                if not isinstance(decorator.func, ast.Attribute):
                    continue
                if not isinstance(decorator.func.value, ast.Name) or decorator.func.value.id != "router":
                    continue
                method = decorator.func.attr.upper()
                if not decorator.args:
                    continue
                first_arg = decorator.args[0]
                if not (isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str)):
                    continue
                route_path = first_arg.value
                endpoint = f"{method} {route_path}"
                # Extract query params and body model
                query_params = []
                body_model = None
                for arg in node.args.args[1:]:  # skip 'self' if present
                    arg_name = arg.arg
                    annotation = ast.unparse(arg.annotation) if arg.annotation else None
                    default = None
                    for default_val in node.args.defaults:
                        if hasattr(default_val, 'value'):
                            default = default_val.value
                    # Heuristic: if annotation is a Pydantic model, treat as body
                    if annotation and hasattr(schemas, annotation):
                        model_cls = getattr(schemas, annotation)
                        if issubclass(model_cls, BaseModel):
                            body_model = {
                                'model': annotation,
                                'fields': [
                                    {
                                        'name': f.name,
                                        'type': f.annotation,
                                        'default': f.default,
                                        'description': f.field_info.description if hasattr(f, 'field_info') else ''
                                    }
                                    for f in model_cls.__fields__.values()
                                ]
                            }
                            continue
                    # Otherwise, treat as query param
                    query_params.append({'name': arg_name, 'type': annotation, 'default': default})
                endpoints[endpoint] = {'query_params': query_params, 'body_model': body_model}
    return endpoints
