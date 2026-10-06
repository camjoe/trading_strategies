from __future__ import annotations

import argparse
import json
import re
import sys
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
    RISK_WRITES_LOCAL,
    RISKS,
    build_example,
    capture_parser,
    describe_arguments,
    make_row,
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
    assert build_example("run", None, [argument]) == "run"


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


def test_only_read_only_entries_are_runnable(payload: dict) -> None:
    runnable = [row for row in payload["commands"] if row["runnable"]]

    assert len(runnable) > 20
    for row in runnable:
        assert row["risk"] == "read-only", row["name"]
        assert row["argv"][0] == "-m", row["name"]


def test_every_entry_carries_the_module_and_subcommand_the_runner_starts(payload: dict) -> None:
    rows = _rows_by_name(payload)

    assert rows["report"]["argv"] == ["-m", "trading.interfaces.cli.main"]
    assert rows["db-migrations status"]["argv"] == ["-m", "scripts.data_ops.manage_db_migrations"]
    assert rows["db-migrations status"]["subcommand"] == "status"
    assert rows["layer-check"]["argv"] == ["-m", "scripts.checks.repo.layer_check"]


def test_slow_or_writing_entries_stay_off_the_ui(payload: dict) -> None:
    rows = _rows_by_name(payload)

    assert rows["backtest-bench"]["risk"] == "read-only"
    assert rows["backtest-bench"]["runnable"] is False
    for name in ("run-suite", "pytest-check", "mypy-check", "ci", "quick", "run-checks quick"):
        assert rows[name]["runnable"] is False, name
    for name in ("create-account", "trade", "daily-paper-trading", "ibkr-web-api-smoke-test"):
        assert rows[name]["runnable"] is False, name


def test_make_row_refuses_a_runnable_entry_that_is_not_read_only() -> None:
    with pytest.raises(ValueError, match="only read-only entries may run"):
        make_row(
            name="x",
            kind=KIND_CLI,
            group="g",
            risk=RISK_WRITES_LOCAL,
            help_text="h",
            invocation="python -m x",
            argv=["-m", "x"],
            subcommand=None,
            arguments=[],
            runnable=True,
        )


def test_tools_with_subcommands_and_curated_bundles_form_families(payload: dict) -> None:
    rows = _rows_by_name(payload)
    families = {family["name"] for family in payload["families"]}

    assert {row["family"] for row in payload["commands"]} - {None} == families
    assert rows["run-checks docs"]["family"] == "run-checks"
    assert rows["db-migrations status"]["family"] == "db-migrations"
    assert rows["launch-demo"]["family"] == rows["launch-ui"]["family"]
    assert rows["layer-check"]["family"] == rows["mypy-check"]["family"]
    assert rows["run-suite"]["family"] is None
    assert rows["fix-checks"]["family"] is None
    assert all(row["family"] is None for row in payload["commands"] if row["kind"] != "tool")


def test_a_family_without_a_summary_fails_the_build(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.documentation_ui.commands import entrypoints

    monkeypatch.setattr(entrypoints, "FAMILIES", {k: v for k, v in entrypoints.FAMILIES.items() if k != "db-admin"})

    with pytest.raises(ValueError, match="db-admin"):
        entrypoints.build_entrypoint_rows()


def test_a_runnable_tool_name_that_does_not_exist_fails_the_build(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.documentation_ui.commands import entrypoints

    monkeypatch.setattr(entrypoints, "RUNNABLE_TOOLS", entrypoints.RUNNABLE_TOOLS | {"no-such-tool"})

    with pytest.raises(ValueError, match="no-such-tool"):
        entrypoints.build_entrypoint_rows()


def test_registry_is_identical_when_the_interpreter_lives_elsewhere(
    payload: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "executable", "/opt/hostedtoolcache/Python/3.14.0/x64/bin/python")
    monkeypatch.setattr(sys, "prefix", "/opt/hostedtoolcache/Python/3.14.0/x64")

    assert registry.build_payload() == payload


def test_an_empty_interpreter_path_does_not_corrupt_the_registry(
    payload: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "executable", "")

    rebuilt = registry.build_payload()

    assert [row["name"] for row in rebuilt["commands"]] == [row["name"] for row in payload["commands"]]
    assert all(row["help"] for row in rebuilt["commands"])


def test_the_interpreter_default_is_recorded_as_a_placeholder(payload: dict) -> None:
    schedules = _rows_by_name(payload)["manage-job-schedules"]
    (python_argument,) = [argument for argument in schedules["arguments"] if argument["dest"] == "python"]

    assert python_argument["default"] == "<python>"


ABSOLUTE_PATH = re.compile(r"(^|[\s=(])([A-Za-z]:[\\/]|/(usr|home|opt|tmp|var|Users|mnt)/)")


def test_no_default_or_help_holds_a_machine_specific_path(payload: dict) -> None:
    for row in payload["commands"]:
        for argument in row["arguments"]:
            for field in ("default", "help"):
                assert not ABSOLUTE_PATH.search(str(argument[field])), (row["name"], argument["dest"], field)
        assert not ABSOLUTE_PATH.search(row["help"]), row["name"]


def test_every_argument_has_a_scope(payload: dict) -> None:
    for row in payload["commands"]:
        for argument in row["arguments"]:
            assert argument["scope"] in {"global", "command"}, row["name"]


def test_example_puts_global_options_before_the_subcommand() -> None:
    arguments = [
        {
            "scope": "global",
            "required": True,
            "positional": False,
            "kind": "value",
            "flags": ["--db"],
            "dest": "db",
            "choices": None,
        },
        {
            "scope": "command",
            "required": True,
            "positional": True,
            "kind": "value",
            "flags": ["rev"],
            "dest": "rev",
            "choices": None,
        },
        {
            "scope": "command",
            "required": False,
            "positional": False,
            "kind": "value",
            "flags": ["--x"],
            "dest": "x",
            "choices": None,
        },
    ]

    assert build_example("python -m tool", "status", arguments) == "python -m tool --db <DB> status <REV>"
    assert build_example("python -m tool", None, arguments[2:]) == "python -m tool"


def test_the_subcommand_is_stored_apart_from_the_module(payload: dict) -> None:
    rows = _rows_by_name(payload)

    assert rows["report"]["subcommand"] == "report"
    assert rows["report"]["argv"] == ["-m", "trading.interfaces.cli.main"]
    assert rows["layer-check"]["subcommand"] is None


def test_check_reports_missing_registry(tmp_path: Path) -> None:
    assert run_commands_reference_check(tmp_path) == 2
