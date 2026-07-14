from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.database_diagrams.html_viewer import render_html


def load_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Schema payload must be a JSON object.")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a self-contained database diagram viewer from a neutral schema JSON payload.",
    )
    parser.add_argument("--schema-json", type=Path, required=True, help="Input neutral schema JSON payload.")
    parser.add_argument("--output", type=Path, required=True, help="Output HTML path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = load_payload(args.schema_json)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_html(payload), encoding="utf-8")
    print(f"Wrote database diagram viewer: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
