"""Normalized schema comparison shared by ``baseline`` and ``verify``.

Implements the Schema Comparison Semantics in
docs/numbered-database-migration-plan.md: "matches revision X" always means
equality under these rules, never byte-identical DDL.

- Tables, columns, foreign keys, unique/primary-key constraints, check
  constraints, and named indexes are compared as sets — physical column order
  is ignored, because databases built additively via ``ALTER TABLE ADD
  COLUMN`` order columns differently than a fresh ``CREATE TABLE``.
- Whitespace and ``IF NOT EXISTS`` are normalized out of compared SQL.
- SQLite internals (``sqlite_*``), auto-generated indexes, and the
  ``alembic_version`` table are ignored.
- ``accounts.rotation_overlay_watchlist``: the DEFAULT literal was frozen per
  database when the probe migration ran, so deployed databases legitimately
  disagree on its value. The comparator requires the default to exist but
  does not compare its value.

Plain ``sqlite3`` introspection only — no Alembic or SQLAlchemy imports, so
the module stays importable everywhere.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from infrastructure.database.schema_version import ALEMBIC_VERSION_TABLE

# (table, column) pairs whose DEFAULT is compared by presence, not value.
DEFAULT_VALUE_PRESENCE_ONLY = frozenset({("accounts", "rotation_overlay_watchlist")})

_PRESENT_SENTINEL = "<default present>"

_APPLICATION_TABLES_QUERY = (
    "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' AND name != ?"
)
_NAMED_INDEXES_QUERY = "SELECT name, tbl_name, sql FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL"
_CHECK_KEYWORD_RE = re.compile(r"\bCHECK\s*\(", flags=re.IGNORECASE)


def _normalize_sql(sql: str) -> str:
    """Collapse whitespace and drop IF NOT EXISTS so formatting cannot drift."""
    collapsed = " ".join(sql.split())
    return re.sub(r"\bIF\s+NOT\s+EXISTS\s+", "", collapsed, flags=re.IGNORECASE)


def _extract_check_clauses(table_sql: str) -> Counter[str]:
    """Return the multiset of normalized CHECK(...) expressions in a CREATE TABLE."""
    normalized = _normalize_sql(table_sql)
    checks: Counter[str] = Counter()
    for match in _CHECK_KEYWORD_RE.finditer(normalized):
        depth = 0
        start = match.end() - 1
        for position in range(start, len(normalized)):
            char = normalized[position]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    checks[normalized[start + 1 : position].strip()] += 1
                    break
    return checks


def _column_entry(table: str, row: Any) -> tuple[str, str, int, str | None, int]:
    name, column_type, not_null, default, primary_key = row[1], row[2], row[3], row[4], row[5]
    if (table, str(name)) in DEFAULT_VALUE_PRESENCE_ONLY and default is not None:
        normalized_default: str | None = _PRESENT_SENTINEL
    elif default is not None:
        normalized_default = " ".join(str(default).split())
    else:
        normalized_default = None
    return (str(name), str(column_type), int(not_null), normalized_default, int(primary_key))


def _table_snapshot(conn: Any, table: str) -> dict[str, Any]:
    columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
    foreign_keys = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    # origin 'u'/'pk' rows are constraint-generated; named CREATE INDEX rows
    # ('c') are compared separately through their normalized SQL.
    constraint_indexes: set[tuple[str, tuple[str, ...]]] = set()
    for index_row in conn.execute(f"PRAGMA index_list({table})").fetchall():
        if str(index_row[3]) not in ("u", "pk"):
            continue
        members = conn.execute(f"PRAGMA index_info({index_row[1]})").fetchall()
        ordered = tuple(str(m[2]) for m in sorted(members, key=lambda m: int(m[0])))
        constraint_indexes.add((str(index_row[3]), ordered))
    table_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return {
        "columns": {_column_entry(table, row) for row in columns},
        "foreign_keys": {
            (str(row[2]), str(row[3]), str(row[4]), str(row[5]).upper(), str(row[6]).upper()) for row in foreign_keys
        },
        "constraints": constraint_indexes,
        "checks": _extract_check_clauses(str(table_sql_row[0]) if table_sql_row else ""),
    }


def snapshot_schema(conn: Any) -> dict[str, Any]:
    """Normalized snapshot of an open database's schema."""
    tables = {str(row[0]) for row in conn.execute(_APPLICATION_TABLES_QUERY, (ALEMBIC_VERSION_TABLE,))}
    snapshot: dict[str, Any] = {"tables": {name: _table_snapshot(conn, name) for name in sorted(tables)}}
    snapshot["indexes"] = {
        str(row[0]): _normalize_sql(str(row[2]))
        for row in conn.execute(_NAMED_INDEXES_QUERY)
        if not str(row[0]).startswith("sqlite_")
    }
    return snapshot


@dataclass(frozen=True)
class SchemaComparison:
    """Result of comparing an actual schema against an expected one."""

    differences: list[str] = field(default_factory=list)

    @property
    def matches(self) -> bool:
        return not self.differences


def _diff_sets(differences: list[str], label: str, expected: set, actual: set) -> None:
    for item in sorted(expected - actual, key=repr):
        differences.append(f"{label}: missing {item!r}")
    for item in sorted(actual - expected, key=repr):
        differences.append(f"{label}: unexpected {item!r}")


def compare_schemas(expected_conn: Any, actual_conn: Any) -> SchemaComparison:
    """Compare *actual* against *expected* under the normalization rules.

    Differences are phrased from the actual database's point of view
    ("missing" = expected but absent, "unexpected" = present but not expected)
    and name the differing table, column, index, FK, or check.
    """
    expected = snapshot_schema(expected_conn)
    actual = snapshot_schema(actual_conn)
    differences: list[str] = []

    expected_tables = set(expected["tables"])
    actual_tables = set(actual["tables"])
    _diff_sets(differences, "tables", expected_tables, actual_tables)

    for table in sorted(expected_tables & actual_tables):
        expected_table = expected["tables"][table]
        actual_table = actual["tables"][table]
        for aspect in ("columns", "foreign_keys", "constraints"):
            _diff_sets(differences, f"table {table} {aspect}", expected_table[aspect], actual_table[aspect])
        if expected_table["checks"] != actual_table["checks"]:
            expected_checks: Counter[str] = expected_table["checks"]
            actual_checks: Counter[str] = actual_table["checks"]
            for clause in sorted((expected_checks - actual_checks).keys()):
                differences.append(f"table {table} checks: missing 'CHECK ({clause})'")
            for clause in sorted((actual_checks - expected_checks).keys()):
                differences.append(f"table {table} checks: unexpected 'CHECK ({clause})'")

    expected_indexes: dict[str, str] = expected["indexes"]
    actual_indexes: dict[str, str] = actual["indexes"]
    _diff_sets(differences, "indexes", set(expected_indexes), set(actual_indexes))
    for name in sorted(set(expected_indexes) & set(actual_indexes)):
        if expected_indexes[name] != actual_indexes[name]:
            differences.append(
                f"index {name}: definition differs (expected '{expected_indexes[name]}', "
                f"actual '{actual_indexes[name]}')"
            )

    return SchemaComparison(differences=differences)
