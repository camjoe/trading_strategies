"""Assemble the self-contained database diagram viewer from static assets.

The viewer's markup, styles, and behavior live as real files in ``assets/``
(``viewer.html``, ``viewer.css``, ``viewer.js``) so they can be edited with
normal HTML/CSS/JS tooling. This module only substitutes the payload and
metadata placeholders and returns the single self-contained HTML document.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

DEFAULT_VIEWER_TITLE = "Database Diagram Viewer"

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def _read_asset(name: str) -> str:
    return (_ASSETS_DIR / name).read_text(encoding="utf-8")


def render_html(payload: dict[str, Any]) -> str:
    payload_json = json.dumps(payload, indent=2, sort_keys=True)
    escaped_payload = html.escape(payload_json, quote=False)
    table_count = len(payload["tables"])
    generated_at = html.escape(str(payload.get("generatedAt", "unknown")))
    viewer_title = html.escape(str(payload.get("title") or DEFAULT_VIEWER_TITLE))
    source_text = html.escape(str(payload.get("source", "schema payload")))
    return (
        _read_asset("viewer.html")
        .replace("__VIEWER_CSS__", _read_asset("viewer.css"))
        .replace("__VIEWER_JS__", _read_asset("viewer.js"))
        .replace("__VIEWER_TITLE__", viewer_title)
        .replace("__GENERATED_AT__", generated_at)
        .replace("__SOURCE_TEXT__", source_text)
        .replace("__TABLE_COUNT__", str(table_count))
        # Payload substitution goes last so placeholder-like strings inside the
        # schema JSON can never be rewritten by the earlier replacements.
        .replace("__SCHEMA_PAYLOAD__", escaped_payload)
    )
