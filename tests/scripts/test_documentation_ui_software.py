from __future__ import annotations

from scripts.documentation_ui.software.registry import parse_requirement_entry


def test_parse_requirement_entry_skips_editable_install() -> None:
    assert parse_requirement_entry("-e .") is None
    assert parse_requirement_entry("--editable .") is None
