from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.documentation_ui.overview import registry
from scripts.documentation_ui.overview.build_registry import run_build
from scripts.documentation_ui.overview.check import run_overview_check


def _make_repo(root: Path, test_functions: int = 5, adrs: tuple[str, ...] = ("001-a.md", "002-b.md")) -> None:
    (root / "apps/paper_trading_web/frontend/src/assets").mkdir(parents=True)
    tests_dir = root / "tests" / "unit"
    tests_dir.mkdir(parents=True)
    body = "\n".join(f"def test_case_{index}():\n    pass\n" for index in range(test_functions))
    (tests_dir / "test_sample.py").write_text(body, encoding="utf-8")
    (tests_dir / "helpers.py").write_text("def test_not_collected():\n    pass\n", encoding="utf-8")
    adr_dir = root / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    for name in (*adrs, "TEMPLATE.adr.md", "README.md"):
        (adr_dir / name).write_text("# adr\n", encoding="utf-8")


def test_count_test_functions_reads_only_test_files_and_nested_tests(tmp_path: Path) -> None:
    _make_repo(tmp_path, test_functions=3)
    (tmp_path / "tests" / "unit" / "test_classes.py").write_text(
        "class TestThing:\n    def test_one(self):\n        pass\n\n    def helper(self):\n        pass\n",
        encoding="utf-8",
    )

    assert registry.count_test_functions(tmp_path / "tests") == 4


def test_count_adrs_ignores_the_template_and_other_files(tmp_path: Path) -> None:
    _make_repo(tmp_path)

    assert registry.count_adrs(tmp_path / "docs" / "adr") == 2


def test_payload_floors_the_test_count_so_one_new_test_does_not_drift(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(registry, "TEST_COUNT_STEP", 4)
    _make_repo(tmp_path, test_functions=5)
    first = registry.build_payload(tmp_path)["python_tests_floor"]
    extra_test = tmp_path / "tests" / "unit" / "test_extra.py"
    extra_test.write_text("def test_extra():\n    pass\n", encoding="utf-8")

    assert first == 4
    assert registry.build_payload(tmp_path)["python_tests_floor"] == 4


def test_payload_reports_tables_strategies_and_adrs(tmp_path: Path) -> None:
    _make_repo(tmp_path)

    payload = registry.build_payload(tmp_path)

    assert payload["database_tables"] > 0
    assert payload["strategies"]["total"] == sum(payload["strategies"]["by_style"].values())
    assert payload["adrs"] == 2


def test_check_passes_after_build_and_fails_on_drift(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    run_build(tmp_path)
    assert run_overview_check(tmp_path) == 0

    path = tmp_path / registry.OVERVIEW_REGISTRY_REL
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["adrs"] += 1
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert run_overview_check(tmp_path) == 1


def test_check_reports_missing_registry(tmp_path: Path) -> None:
    assert run_overview_check(tmp_path) == 2


@pytest.mark.parametrize("name", ["001-a.md", "123-long-name.md"])
def test_adr_pattern_accepts_numbered_files(name: str) -> None:
    assert registry.ADR_PATTERN.match(name)
