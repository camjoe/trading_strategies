from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

from common.paths.repo_paths import get_repo_root
from trading.database.db_init import init_schema

DB_SCHEMA_DOC_REL = "docs/reference/db-schema.md"

# Matches Quick Reference table rows: | `table_name` | purpose | FK |
# The 3-column QR rows have 4 pipe chars; 2-column semantic-note rows have 3.
QR_TABLE_RE = re.compile(r"^\|\s+`(\w+)`\s+\|")


def _schema_table_names() -> set[str]:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def _quick_reference_tables(content: str) -> set[str]:
    """Table names from the 3-column Quick Reference rows (skips 2-column semantic-note rows)."""
    tables: set[str] = set()
    for line in content.splitlines():
        if line.count("|") < 4:  # QR rows have 3 cols = 4 pipes; 2-col note rows have 3
            continue
        match = QR_TABLE_RE.match(line)
        if match:
            tables.add(match.group(1))
    return tables


def run_db_schema_check(repo_root: Path, *, enforce: bool = False) -> int:
    doc_path = repo_root / DB_SCHEMA_DOC_REL
    if not doc_path.is_file():
        print(f"ERROR: schema doc not found: {doc_path}")
        return 2

    content = doc_path.read_text(encoding="utf-8")
    actual_tables = _schema_table_names()
    qr_tables = _quick_reference_tables(content)

    undocumented = sorted(actual_tables - qr_tables)
    stale_qr = sorted(qr_tables - actual_tables)

    print("DB Schema Drift Check")
    print(f"Doc:  {DB_SCHEMA_DOC_REL}")
    print(f"Mode: {'enforced' if enforce else 'advisory'}")

    issues: list[str] = []
    if undocumented:
        issues.append(f"Quick Reference missing {len(undocumented)} table(s): {', '.join(undocumented)}")
    if stale_qr:
        issues.append(f"Quick Reference has {len(stale_qr)} stale row(s) (no matching table): {', '.join(stale_qr)}")

    if issues:
        print("\nFindings:")
        for issue in issues:
            print(f"  - {issue}")
        if enforce:
            print("\nFAIL: db schema check failed in enforce mode.")
            return 1
        print(f"\nWARN: update the Quick Reference table in {DB_SCHEMA_DOC_REL}.")
        return 0

    print(f"\nPASS: Quick Reference covers all {len(actual_tables)} tables.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            f"Check that the Quick Reference table in {DB_SCHEMA_DOC_REL} "
            "covers every table in the current schema. "
            "Advisory by default; use --enforce to fail non-zero on drift."
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to detected workspace root.",
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Exit non-zero when drift is found (default: advisory, always exit 0).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_db_schema_check(repo_root=repo_root, enforce=args.enforce)


if __name__ == "__main__":
    raise SystemExit(main())
