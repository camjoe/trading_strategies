from __future__ import annotations

from scripts.documentation_ui.api.registry import build_registry


def _route(module: str) -> dict[str, str]:
    return {
        "method": "POST",
        "path": "/api/catalog/run",
        "handler": "api_catalog_run",
        "module": module,
        "group": "Catalog Endpoints",
        "description": "From the docstring.",
    }


def test_group_always_follows_the_route_module_so_a_rebuild_fixes_a_stale_group() -> None:
    rows = build_registry(
        {"POST /api/catalog/run": _route("catalog")}, {"POST /api/catalog/run": {"description": "x"}}
    )

    assert rows[0]["group"] == "Catalog Endpoints"


def test_a_curated_description_survives_a_rebuild() -> None:
    rows = build_registry(
        {"POST /api/catalog/run": _route("catalog")},
        {"POST /api/catalog/run": {"description": "Curated."}},
    )

    assert rows[0]["description"] == "Curated."


def test_a_new_route_takes_its_description_from_the_docstring() -> None:
    rows = build_registry({"POST /api/catalog/run": _route("catalog")}, {})

    assert rows[0]["description"] == "From the docstring."
