"""Command catalog endpoint.

POST /api/catalog/run — run one read-only catalog entry and return its output

Which entries may run, and how their arguments are assembled, lives in
``paper_trading_web.backend.services.catalog_runner``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..schemas import CatalogRunRequest
from ..services.catalog_runner import run_entry

router = APIRouter()


@router.post("/api/catalog/run")
def api_catalog_run(body: CatalogRunRequest) -> dict[str, Any]:
    """Run one read-only entry from the command catalog and return its exit code and output."""
    return run_entry(body.name, body.values)
