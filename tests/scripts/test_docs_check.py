from __future__ import annotations

from pathlib import Path

from scripts.checks.docs import docs_check


def test_docs_check_runs_expected_steps_in_order(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        docs_check,
        "run_readme_consistency",
        lambda **kwargs: calls.append(f"readme:{kwargs['enforce_style']}") or 0,
    )
    monkeypatch.setattr(docs_check, "run_maps_check", lambda **kwargs: calls.append("maps") or 0)
    monkeypatch.setattr(docs_check, "run_link_check", lambda **kwargs: calls.append("links") or 0)
    monkeypatch.setattr(docs_check, "run_module_ref_check", lambda **kwargs: calls.append("modules") or 0)
    monkeypatch.setattr(docs_check, "run_db_schema_check", lambda **kwargs: calls.append("db") or 0)
    monkeypatch.setattr(docs_check, "run_doc_header_check", lambda **kwargs: calls.append("headers") or 0)
    monkeypatch.setattr(docs_check, "run_doc_naming_check", lambda **kwargs: calls.append("naming") or 0)
    monkeypatch.setattr(docs_check, "run_reference_docs_check", lambda **kwargs: calls.append("reference") or 0)

    assert docs_check.run_docs_check(Path("."), enforce=True, quiet=True) == 0
    assert calls == [
        "readme:True",
        "maps",
        "links",
        "modules",
        "db",
        "headers",
        "naming",
        "reference",
    ]


def test_docs_check_returns_first_failure(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(docs_check, "run_readme_consistency", lambda **kwargs: calls.append("readme") or 0)
    monkeypatch.setattr(docs_check, "run_maps_check", lambda **kwargs: calls.append("maps") or 2)
    monkeypatch.setattr(docs_check, "run_link_check", lambda **kwargs: calls.append("links") or 0)

    assert docs_check.run_docs_check(Path(".")) == 2
    assert calls == ["readme", "maps"]


def test_docs_check_can_skip_reference_docs(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(docs_check, "run_readme_consistency", lambda **kwargs: calls.append("readme") or 0)
    monkeypatch.setattr(docs_check, "run_maps_check", lambda **kwargs: calls.append("maps") or 0)
    monkeypatch.setattr(docs_check, "run_link_check", lambda **kwargs: calls.append("links") or 0)
    monkeypatch.setattr(docs_check, "run_module_ref_check", lambda **kwargs: calls.append("modules") or 0)
    monkeypatch.setattr(docs_check, "run_db_schema_check", lambda **kwargs: calls.append("db") or 0)
    monkeypatch.setattr(docs_check, "run_doc_header_check", lambda **kwargs: calls.append("headers") or 0)
    monkeypatch.setattr(docs_check, "run_doc_naming_check", lambda **kwargs: calls.append("naming") or 0)
    monkeypatch.setattr(docs_check, "run_reference_docs_check", lambda **kwargs: calls.append("reference") or 0)

    assert docs_check.run_docs_check(Path("."), include_reference_docs=False) == 0
    assert calls == [
        "readme",
        "maps",
        "links",
        "modules",
        "db",
        "headers",
        "naming",
    ]
