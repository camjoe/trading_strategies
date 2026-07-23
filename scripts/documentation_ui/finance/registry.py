from __future__ import annotations

import html
from pathlib import Path
from typing import Any

FINANCE_DOC_REL = "docs/reference/financial-market-knowledge.md"
FINANCE_REGISTRY_REL = "apps/paper_trading_web/frontend/src/assets/finance.json"

VALID_USE_VALUES = {"both", "glossary", "ui"}
TABLE_COLUMNS = ["Term", "Use", "Definition", "UI Label"]


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [html.unescape(cell.strip()) for cell in stripped.strip("|").split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(set(cell.replace(" ", "")) <= {"-", ":"} for cell in cells)


def _normalize_group(heading: str) -> str:
    group_map = {
        "Data and Backtesting Integrity": "Backtesting and Validation",
        "Execution and Risk Controls": "Execution and Risk Controls",
        "Options and Volatility": "Options and Volatility",
        "Performance and Risk": "Performance and Risk",
        "Technical Analysis": "Technical Analysis",
        "Trading Strategies": "Trading Strategies",
        "Asset Classes": "Asset Classes",
    }
    return group_map.get(heading, heading)


def parse_finance_reference(path: Path) -> list[dict[str, str]]:
    """Parse finance glossary tables from the canonical markdown reference."""
    terms: list[dict[str, str]] = []
    current_group: str | None = None
    in_table = False

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if line.startswith("## "):
            current_group = _normalize_group(line.removeprefix("## ").strip())
            in_table = False
            continue

        cells = _split_table_row(line)
        if not cells:
            in_table = False
            continue

        if cells == TABLE_COLUMNS:
            if current_group is None:
                raise ValueError(f"{path}:{line_number}: term table appears before a group heading")
            in_table = True
            continue

        if _is_separator_row(cells):
            continue

        if not in_table:
            continue

        if len(cells) != len(TABLE_COLUMNS):
            raise ValueError(f"{path}:{line_number}: expected {len(TABLE_COLUMNS)} table cells, got {len(cells)}")

        term, use, definition, ui_label = cells
        if not term:
            raise ValueError(f"{path}:{line_number}: term is required")
        if use not in VALID_USE_VALUES:
            raise ValueError(f"{path}:{line_number}: use must be one of {sorted(VALID_USE_VALUES)}")
        if not definition:
            raise ValueError(f"{path}:{line_number}: definition is required")

        row = {
            "term": term,
            "group": current_group or "",
            "use": use,
            "definition": definition,
        }
        if ui_label:
            row["ui_label"] = ui_label
        terms.append(row)

    return terms


def build_payload(terms: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "editing_notes": (
            "Edit financial and market terms in docs/reference/financial-market-knowledge.md, "
            "then run python -m scripts.documentation_ui.sync."
        ),
        "terms": terms,
    }
