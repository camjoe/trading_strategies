from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path
from typing import Any

from infrastructure.database import migration_runner
from trading.domain.strategies.registry import STRATEGY_REGISTRY

OVERVIEW_REGISTRY_REL = "apps/paper_trading_web/frontend/src/assets/overview.json"
ADR_PATTERN = re.compile(r"^\d{3}-.+\.md$")

# The test count is floored to this step so adding one test does not make the asset drift.
TEST_COUNT_STEP = 100


def count_test_functions(tests_dir: Path) -> int:
    count = 0
    for path in tests_dir.rglob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        count += sum(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
            for node in ast.walk(tree)
        )
    return count


def count_database_tables() -> int:
    conn = migration_runner.build_reference_connection()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
        ).fetchall()
    finally:
        conn.close()
    return len(rows)


def count_adrs(adr_dir: Path) -> int:
    return sum(1 for path in adr_dir.iterdir() if ADR_PATTERN.match(path.name))


def build_payload(repo_root: Path) -> dict[str, Any]:
    styles = Counter(spec.strategy_style for spec in STRATEGY_REGISTRY.values())
    tests = count_test_functions(repo_root / "tests")
    return {
        "schema_version": 1,
        "database_tables": count_database_tables(),
        "strategies": {"total": sum(styles.values()), "by_style": dict(sorted(styles.items()))},
        "adrs": count_adrs(repo_root / "docs" / "adr"),
        "python_tests_floor": tests // TEST_COUNT_STEP * TEST_COUNT_STEP,
    }
