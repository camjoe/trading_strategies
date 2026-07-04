from __future__ import annotations

from pathlib import Path

import pytest

from scripts.fixes.db_schema_fix import PLACEHOLDER_PURPOSE, fix_quick_reference, run_db_schema_fix


# Quick Reference (3-column rows), a table-count prose line, and a 2-column semantic-note
# row that must never be touched by the fixer.
QR_DOC = (
    "## Quick Reference\n"
    "\n"
    "2 tables. One row per table.\n"
    "\n"
    "| Table | Purpose | Key relationships |\n"
    "|---|---|---|\n"
    "| `accounts` | config | — |\n"
    "| `trades` | trades | → `accounts` |\n"
    "\n"
    "## Semantic Notes\n"
    "### `accounts`\n"
    "| Column | Note |\n"
    "| `initial_cash` | deposit model |\n"
)


def _write_doc(repo_root: Path, content: str) -> Path:
    path = repo_root / "docs/reference/db-schema.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_in_sync_content_is_unchanged() -> None:
    new_content, added, removed = fix_quick_reference(QR_DOC, {"accounts", "trades"})
    assert new_content == QR_DOC
    assert added == []
    assert removed == []


def test_stale_row_is_removed_and_count_updated() -> None:
    new_content, added, removed = fix_quick_reference(QR_DOC, {"accounts"})
    assert removed == ["trades"]
    assert added == []
    assert "| `trades` |" not in new_content
    assert "1 tables. One row per table." in new_content
    # The 2-column semantic-note row is not a Quick Reference row and stays.
    assert "| `initial_cash` | deposit model |" in new_content


def test_missing_table_gets_scaffold_row_after_last_row() -> None:
    new_content, added, removed = fix_quick_reference(QR_DOC, {"accounts", "trades", "new_table"})
    assert added == ["new_table"]
    assert removed == []
    assert f"| `new_table` | {PLACEHOLDER_PURPOSE} | — |" in new_content
    assert "3 tables. One row per table." in new_content
    # Scaffold row lands inside the Quick Reference table, before the Semantic Notes section.
    assert new_content.index("`new_table`") < new_content.index("## Semantic Notes")


def test_no_anchor_rows_skips_additions() -> None:
    doc = "## Quick Reference\n\nno table here\n"
    new_content, added, removed = fix_quick_reference(doc, {"accounts"})
    assert added == []
    assert removed == []
    assert new_content == doc


def test_run_writes_fixed_doc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc_path = _write_doc(tmp_path, QR_DOC)
    monkeypatch.setattr(
        "scripts.fixes.db_schema_fix._schema_table_names",
        lambda: {"accounts", "new_table"},  # trades stale, new_table missing
    )

    assert run_db_schema_fix(repo_root=tmp_path) == 0

    content = doc_path.read_text(encoding="utf-8")
    assert "| `trades` |" not in content
    assert f"| `new_table` | {PLACEHOLDER_PURPOSE} | — |" in content


def test_run_errors_when_doc_missing(tmp_path: Path) -> None:
    assert run_db_schema_fix(repo_root=tmp_path) == 2
