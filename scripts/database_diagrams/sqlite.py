from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.database_diagrams.html_viewer import render_html
from scripts.database_diagrams.sqlite_introspection import build_payload_from_database_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect a SQLite database and build a neutral schema payload or HTML diagram viewer.",
    )
    parser.add_argument("--database", type=Path, required=True, help="SQLite database file to inspect.")
    parser.add_argument("--output-json", type=Path, help="Optional neutral schema JSON output path.")
    parser.add_argument("--output-html", type=Path, help="Optional self-contained HTML viewer output path.")
    parser.add_argument("--title", default="Database Diagram Viewer", help="Viewer title.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output_json is None and args.output_html is None:
        raise SystemExit("Provide --output-json, --output-html, or both.")

    payload = build_payload_from_database_path(args.database, title=args.title)

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Wrote schema payload: {args.output_json}")

    if args.output_html is not None:
        args.output_html.parent.mkdir(parents=True, exist_ok=True)
        args.output_html.write_text(render_html(payload), encoding="utf-8")
        print(f"Wrote database diagram viewer: {args.output_html}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
