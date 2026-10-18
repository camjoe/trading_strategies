"""Command catalog endpoint.

POST /api/catalog/run — run one read-only catalog entry and return its output

Which entries may run, and how their arguments are assembled, lives in
``paper_trading_web.backend.services.catalog_runner``.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request

from ..schemas import CatalogRunRequest
from ..services.catalog_runner import run_entry

router = APIRouter()

LOCAL_HOSTNAMES = frozenset({"127.0.0.1", "localhost", "::1"})


def require_local_origin(request: Request) -> None:
    """Refuse a browser request that comes from a page served somewhere else.

    The API allows every origin, so without this check any web page open in the
    operator's browser could start a command. Requests with no Origin header
    (curl, scripts, tests) pass.
    """
    origin = request.headers.get("origin")
    if origin is not None and urlparse(origin).hostname not in LOCAL_HOSTNAMES:
        raise HTTPException(status_code=403, detail="Commands can run only from a page served on this machine.")


@router.post("/api/catalog/run", dependencies=[Depends(require_local_origin)])
def api_catalog_run(body: CatalogRunRequest) -> dict[str, Any]:
    """Run one read-only entry from the command catalog and return its exit code and output."""
    return run_entry(body.name, body.values)
