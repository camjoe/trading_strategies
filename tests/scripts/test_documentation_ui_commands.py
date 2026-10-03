from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from common.git import get_repo_root
from scripts.documentation_ui.commands import registry
from scripts.documentation_ui.commands.build_registry import run_build
from scripts.documentation_ui.commands.check import run_commands_reference_check
from scripts.documentation_ui.commands.entrypoints import check_coverage, discover_main_modules
from scripts.documentation_ui.commands.introspect import (
    KIND_CLI,
    KIND_JOB,
    RISKS,
    build_example,
    capture_parser,
    describe_arguments,
    subparsers_action,
)
from trading.interfaces.cli.commands.builder import build_parser
from trading.interfaces.runtime.scheduling.job_catalog import JOB_CATALOG


@pytest.fixture(scope="module")
def payload() -> dict:
    return registry.build_payload()


def _rows_by_name(payload: dict) -> dict[str, dict]:
    return {row["name"]: row for row in payload["commands"]}


def test_registry_covers_every_cli_command(payload: dict) -> None:
    cli_names = {row["name"] for row in payload["commands"] if row["kind"] == KIND_CLI}
    action = subparsers_action(build_parser())

    assert action is not None
    assert cli_names == set(action.choices)


def test_names_are_unique_and_every_row_is_classified(payload: dict) -> None:
    names = [row["name"] for row in payload["commands"]]
    group_names = {group["name"] for group in payload["groups"]}

    assert len(names) == len(set(names))
    for row in payload["commands"]:
        assert row["risk"] in RISKS
        assert row["group"] in group_names
        assert row["help"]


def test_each_group_belongs_to_one_kind(payload: dict) -> None:
    group_names = [group["name"] for group in payload["groups"]]

    assert len(group_names) == len(set(group_names))


def test_scheduled_jobs_report_their_catalog_schedule(payload: dict) -> None:
    jobs = {row["module"]: row for row in payload["commands"] if row["kind"] == KIND_JOB}

    for definition in JOB_CATALOG.values():
        assert jobs[definition.module]["schedule"] == definition.schedule_kind


def test_registry_holds_no_machine_specific_paths(payload: dict) -> None:
    text = json.dumps(payload)

    assert str(get_repo_root(__file__)) not in text
    assert "Users" not in text


def test_unclassified_cli_command_fails_the_build() -> None:
    with pytest.raises(ValueError, match="exactly one risk table"):
        registry._risk_for("not-a-real-command")


def test_example_lists_required_arguments_only(payload: dict) -> None:
    rows = _rows_by_name(payload)

    assert rows["snapshot"]["example"] == f"{registry.CLI_INVOCATION} snapshot --account <ACCOUNT>"
    assert "--type hold" in rows["advisor-record"]["example"]


def test_positional_arguments_appear_without_a_flag(payload: dict) -> None:
    assert _rows_by_name(payload)["db-admin delete-account"]["example"].endswith("delete-account <ACCOUNT>")


def test_capture_parser_returns_the_parser_without_running_the_body() -> None:
    ran: list[str] = []

    def entrypoint() -> int:
        parser = argparse.ArgumentParser(description="demo")
        parser.add_argument("--count", type=int, default=3, help="how many")
        parser.parse_args()
        ran.append("body")
        return 0

    parser = capture_parser(entrypoint)

    assert ran == []
    assert parser.description == "demo"
    (argument,) = describe_arguments(parser)
    assert argument["flags"] == ["--count"]
    assert argument["type"] == "int"
    assert argument["default"] == 3
    assert build_example("run", [argument]) == "run"


def test_capture_parser_restores_argparse_and_rejects_entrypoints_that_never_parse() -> None:
    original = argparse.ArgumentParser.parse_args

    with pytest.raises(RuntimeError, match="without parsing arguments"):
        capture_parser(lambda: 0)

    assert argparse.ArgumentParser.parse_args is original


def test_coverage_check_flags_unlisted_and_stale_modules() -> None:
    discovered = {"scripts.new_tool": Path("scripts/new_tool.py"), "scripts.known": Path("scripts/known.py")}

    with pytest.raises(ValueError, match="scripts.new_tool"):
        check_coverage(discovered, {"scripts.known"})
    with pytest.raises(ValueError, match="scripts.gone"):
        check_coverage(discovered, {"scripts.known", "scripts.new_tool", "scripts.gone"})


def test_every_runnable_module_is_listed() -> None:
    discovered = discover_main_modules(get_repo_root(__file__))
    listed = {row["module"] for row in registry.build_payload()["commands"] if row["module"]}

    check_coverage(discovered, listed)


def test_check_passes_after_build_and_fails_on_drift(tmp_path: Path) -> None:
    (tmp_path / "apps/paper_trading_web/frontend/src/assets").mkdir(parents=True)

    run_build(tmp_path)
    assert run_commands_reference_check(tmp_path) == 0

    registry_path = tmp_path / registry.COMMANDS_REGISTRY_REL
    registry_path.write_text(registry_path.read_text(encoding="utf-8").replace('"snapshot"', '"snapshot-gone"', 1))
    assert run_commands_reference_check(tmp_path) == 1


def test_check_reports_missing_registry(tmp_path: Path) -> None:
    assert run_commands_reference_check(tmp_path) == 2
