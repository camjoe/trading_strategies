from __future__ import annotations

from pathlib import Path

import pytest

from scripts.checks.docs.db_schema_check import (
    _quick_reference_tables,
    _schema_table_names,
    run_db_schema_check,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

# A Quick Reference (3-column rows) plus a 2-column semantic-note row that must be ignored.
QR_DOC = (
    "## Quick Reference\n"
    "| Table | Purpose | Key relationships |\n"
    "|---|---|---|\n"
    "| `accounts` | config | — |\n"
    "| `trades` | trades | → `accounts` |\n"
    "## Semantic Notes\n"
    "### `accounts`\n"
    "| Column | Note |\n"
    "| `initial_cash` | deposit model |\n"
)


def _write_doc(repo_root: Path, content: str) -> None:
    path = repo_root / "docs/reference/db-schema.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_quick_reference_tables_parses_qr_rows_only() -> None:
    # The 2-column `initial_cash` semantic-note row and the header are excluded.
    assert _quick_reference_tables(QR_DOC) == {"accounts", "trades"}


def test_schema_table_names_returns_live_tables() -> None:
    tables = _schema_table_names()
    assert {"accounts", "orders", "order_fills"} <= tables
    assert "trades" not in tables
    assert len(tables) > 10


def test_run_advisory_returns_zero_on_real_repo() -> None:
    """Advisory mode never fails the build; the real Quick Reference should also be in sync."""
    assert run_db_schema_check(repo_root=PROJECT_ROOT) == 0


def test_enforce_flags_table_missing_from_quick_reference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_doc(tmp_path, QR_DOC)  # documents accounts, trades
    monkeypatch.setattr(
        "scripts.checks.docs.db_schema_check._schema_table_names",
        lambda: {"accounts", "trades", "new_table"},  # new_table undocumented
    )
    assert run_db_schema_check(repo_root=tmp_path, enforce=True) == 1


def test_enforce_flags_stale_quick_reference_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_doc(tmp_path, QR_DOC)  # documents accounts, trades
    monkeypatch.setattr(
        "scripts.checks.docs.db_schema_check._schema_table_names",
        lambda: {"accounts"},  # `trades` no longer exists -> stale doc row
    )
    assert run_db_schema_check(repo_root=tmp_path, enforce=True) == 1


def test_advisory_returns_zero_even_with_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_doc(tmp_path, QR_DOC)
    monkeypatch.setattr(
        "scripts.checks.docs.db_schema_check._schema_table_names",
        lambda: {"accounts", "trades", "new_table"},
    )
    assert run_db_schema_check(repo_root=tmp_path) == 0
