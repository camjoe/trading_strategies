import json
from pathlib import Path

from scripts.forge import tools

SETTINGS = Path(__file__).resolve().parents[2] / ".claude" / "settings.json"


def _permissions() -> dict[str, list[str]]:
    return json.loads(SETTINGS.read_text(encoding="utf-8"))["permissions"]


def _inner(rule: str, tool: str) -> str:
    return rule.removeprefix(f"{tool}(").removesuffix(")")


def test_the_file_holds_only_deny_and_ask_rules() -> None:
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))

    assert list(settings) == ["permissions"]
    assert sorted(settings["permissions"]) == ["ask", "deny"]


def test_every_bash_rule_has_a_powershell_twin_and_the_other_way_round() -> None:
    permissions = _permissions()

    for kind, rules in permissions.items():
        bash = {_inner(rule, "Bash") for rule in rules if rule.startswith("Bash(")}
        powershell = {_inner(rule, "PowerShell") for rule in rules if rule.startswith("PowerShell(")}
        assert bash == powershell, kind


def test_ask_rules_for_git_and_gh_are_already_denied_to_unattended_agents() -> None:
    denied = tools.DENIED_TOOLS.split(",")

    for rule in _permissions()["ask"]:
        if not rule.startswith("Bash("):
            continue
        words = _inner(rule, "Bash").split()
        prefixes = [" ".join(words[:count]) for count in (1, 2)]
        assert any(f"Bash({prefix}:*)" in denied for prefix in prefixes), rule


def test_env_files_are_unreadable_except_the_tracked_examples() -> None:
    deny = _permissions()["deny"]

    assert "Read(.env)" in deny and "Read(.env.*)" in deny
    assert deny.index("Read(!.env.example)") > deny.index("Read(.env.*)")


def test_force_pushes_are_denied() -> None:
    deny = _permissions()["deny"]

    for tool in ("Bash", "PowerShell"):
        assert f"{tool}(git push --force *)" in deny and f"{tool}(git push -f *)" in deny
