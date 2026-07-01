from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.documentation_ui.finance.check import run_finance_reference_check
from scripts.documentation_ui.finance.registry import build_payload, parse_finance_reference


def _write_finance_doc(path: Path, rows: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Financial and Market Knowledge\n\n"
        "Type: notes\n"
        "Status: Active\n"
        "Created: 2026-06-30\n"
        "Last Reviewed: 2026-06-30\n"
        "Purpose: Test doc.\n\n"
        "## Performance and Risk\n\n"
        "| Term | Use | Definition | UI Label |\n"
        "|---|---|---|---|\n"
        f"{rows}",
        encoding="utf-8",
    )


def test_parse_finance_reference_preserves_order_and_optional_ui_label(tmp_path: Path) -> None:
    doc_path = tmp_path / "finance.md"
    _write_finance_doc(
        doc_path,
        "| Alpha | both | Excess return vs. benchmark. |  |\n"
        "| DTE | ui | Days until expiration. | DTE (Days to Expiration) |\n",
    )

    assert parse_finance_reference(doc_path) == [
        {
            "term": "Alpha",
            "group": "Performance and Risk",
            "use": "both",
            "definition": "Excess return vs. benchmark.",
        },
        {
            "term": "DTE",
            "group": "Performance and Risk",
            "use": "ui",
            "definition": "Days until expiration.",
            "ui_label": "DTE (Days to Expiration)",
        },
    ]


def test_parse_finance_reference_accepts_glossary_use(tmp_path: Path) -> None:
    doc_path = tmp_path / "finance.md"
    _write_finance_doc(doc_path, "| Beta | glossary | Market sensitivity. |  |\n")

    terms = parse_finance_reference(doc_path)

    assert terms[0]["use"] == "glossary"


def test_parse_finance_reference_rejects_unknown_use(tmp_path: Path) -> None:
    doc_path = tmp_path / "finance.md"
    _write_finance_doc(doc_path, "| Beta | hidden | Market sensitivity. |  |\n")

    with pytest.raises(ValueError, match="use must be one of"):
        parse_finance_reference(doc_path)


def test_build_payload_uses_schema_version_two() -> None:
    terms = [{"term": "Alpha", "group": "Performance and Risk", "use": "both", "definition": "Excess return."}]

    payload = build_payload(terms)

    assert payload["schema_version"] == 2
    assert payload["terms"] == terms
    assert "financial-market-knowledge.md" in str(payload["editing_notes"])


def test_finance_reference_check_detects_drift(tmp_path: Path) -> None:
    doc_rel = "docs/reference/financial-market-knowledge.md"
    registry_rel = "apps/paper_trading_web/frontend/src/assets/finance.json"
    doc_path = tmp_path / doc_rel
    registry_path = tmp_path / registry_rel
    _write_finance_doc(doc_path, "| Alpha | both | Excess return vs. benchmark. |  |\n")
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps({"schema_version": 2, "terms": []}), encoding="utf-8")

    assert run_finance_reference_check(tmp_path, registry_rel, doc_rel) == 1
