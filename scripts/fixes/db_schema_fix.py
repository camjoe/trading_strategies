from __future__ import annotations

import argparse
import re
from pathlib import Path

from common.git import get_repo_root
from scripts.checks.docs.db_schema_check import (
    DB_SCHEMA_DOC_REL,
    QR_TABLE_RE,
    _schema_table_names,
)

# Fix counterpart of scripts.checks.docs.db_schema_check. Stale Quick Reference rows are
# removed outright; tables missing from the Quick Reference are appended as scaffold rows
# whose Purpose is a TODO placeholder — the row structure is deterministic, the prose is not.

PLACEHOLDER_PURPOSE = "TODO — describe this table"

# The prose line above the Quick Reference table stating the table count ("25 tables. ...").
TABLE_COUNT_RE = re.compile(r"^\d+ tables\.")


def _scaffold_row(table: str) -> str:
    return f"| `{table}` | {PLACEHOLDER_PURPOSE} | — |"


def fix_quick_reference(content: str, actual_tables: set[str]) -> tuple[str, list[str], list[str]]:
    """Return (new content, added table names, removed table names).

    Rows are matched with the same rule as the check (3-column Quick Reference rows only),
    so 2-column semantic-note rows are never touched. Scaffold rows for missing tables are
    appended after the last Quick Reference row; the table-count prose line is refreshed.
    """
    documented: set[str] = set()
    last_row_index: int | None = None
    kept: list[str] = []
    removed: list[str] = []
    for line in content.splitlines():
        match = QR_TABLE_RE.match(line) if line.count("|") >= 4 else None
        if match:
            name = match.group(1)
            documented.add(name)
            if name not in actual_tables:
                removed.append(name)
                continue
            kept.append(line)
            last_row_index = len(kept) - 1
            continue
        kept.append(line)

    added = sorted(actual_tables - documented)
    if added:
        if last_row_index is None:
            print("ERROR: no Quick Reference rows found to anchor scaffold rows; add rows manually.")
            added = []
        else:
            kept[last_row_index + 1 : last_row_index + 1] = [_scaffold_row(table) for table in added]

    for index, line in enumerate(kept):
        if TABLE_COUNT_RE.match(line):
            kept[index] = TABLE_COUNT_RE.sub(f"{len(actual_tables)} tables.", line)
            break

    new_content = "\n".join(kept)
    if content.endswith("\n"):
        new_content += "\n"
    return new_content, added, sorted(removed)


def run_db_schema_fix(repo_root: Path) -> int:
    doc_path = repo_root / DB_SCHEMA_DOC_REL
    if not doc_path.is_file():
        print(f"ERROR: schema doc not found: {doc_path}")
        return 2

    content = doc_path.read_text(encoding="utf-8")
    new_content, added, removed = fix_quick_reference(content, _schema_table_names())
    if new_content != content:
        doc_path.write_text(new_content, encoding="utf-8")

    if removed:
        print(f"Removed stale Quick Reference row(s): {', '.join(removed)}")
    if added:
        print(f"Added scaffold row(s) — fill in each Purpose: {', '.join(added)}")
    if not (added or removed):
        print("Quick Reference already in sync.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            f"Sync the Quick Reference table in {DB_SCHEMA_DOC_REL} with the current schema: "
            "remove stale rows and append TODO scaffold rows for undocumented tables."
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to detected workspace root.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_db_schema_fix(repo_root=repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
