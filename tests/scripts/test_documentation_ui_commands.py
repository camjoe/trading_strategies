from __future__ import annotations

import pytest

from scripts.documentation_ui.commands import registry
from scripts.documentation_ui.commands.build_registry import run_build
from scripts.documentation_ui.commands.check import run_commands_reference_check
from trading.interfaces.cli.commands.builder import build_parser


def _cli_command_names() -> set[str]:
    parser = build_parser()
    return set(registry._subparsers_action(parser).choices)


def test_registry_covers_every_cli_command() -> None:
    names = [row["name"] for row in registry.build_command_rows()]

    assert len(names) == len(set(names))
    assert set(names) == _cli_command_names()


def test_every_command_has_a_known_risk_and_group() -> None:
    for row in registry.build_command_rows():
        assert row["risk"] in {registry.RISK_READ_ONLY, registry.RISK_WRITES_LOCAL}
        assert row["group"] in registry.GROUP_ADDERS
        assert row["help"]


def test_unclassified_command_fails_the_build() -> None:
    with pytest.raises(ValueError, match="exactly one risk table"):
        registry._risk_for("not-a-real-command")


def test_example_lists_required_arguments_only() -> None:
    rows = {row["name"]: row for row in registry.build_command_rows()}

    example = rows["snapshot"]["example"]

    assert example == f"{registry.CLI_INVOCATION} snapshot --account <ACCOUNT>"


def test_example_uses_first_choice_for_choice_arguments() -> None:
    rows = {row["name"]: row for row in registry.build_command_rows()}

    assert "--type hold" in rows["advisor-record"]["example"]


def test_check_passes_after_build_and_fails_on_drift(tmp_path) -> None:
    (tmp_path / "apps/paper_trading_web/frontend/src/assets").mkdir(parents=True)

    run_build(tmp_path)
    assert run_commands_reference_check(tmp_path) == 0

    registry_path = tmp_path / registry.COMMANDS_REGISTRY_REL
    registry_path.write_text(registry_path.read_text(encoding="utf-8").replace('"snapshot"', '"snapshot-gone"', 1))
    assert run_commands_reference_check(tmp_path) == 1


def test_check_reports_missing_registry(tmp_path) -> None:
    assert run_commands_reference_check(tmp_path) == 2
