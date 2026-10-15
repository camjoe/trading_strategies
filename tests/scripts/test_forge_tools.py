import re

from scripts.forge import tools

# The verb in a `Bash(git <verb>:*)` tool rule.
GIT_RULE = re.compile(r"Bash\(git (\w+):\*\)")


class TestToolLimits:
    def test_the_agent_may_remove_and_move_files_through_git_and_still_may_not_reset_or_push(self) -> None:
        allowed = tools.ALLOWED_TOOLS.split(",")
        denied = tools.DENIED_TOOLS.split(",")

        assert "Bash(git rm:*)" in allowed and "Bash(git mv:*)" in allowed
        assert "Bash(git reset:*)" in denied and "Bash(git push:*)" in denied

    def test_python_is_allowed_only_for_the_checks_and_the_test_runner(self) -> None:
        allowed = tools.ALLOWED_TOOLS.split(",")

        assert "Bash(python:*)" not in allowed and "Bash(.venv/Scripts/python.exe:*)" not in allowed
        assert "Bash(.venv/Scripts/python.exe -m scripts.run_checks:*)" in allowed
        assert "Bash(python -m pytest:*)" in allowed

    def test_the_agent_cannot_write_into_git_or_reach_the_remote(self) -> None:
        denied = tools.DENIED_TOOLS.split(",")

        for item in ("Edit(.git/**)", "Write(.git/**)", "Bash(gh:*)", "Bash(git push:*)", "Bash(git config:*)"):
            assert item in denied

    def test_nothing_is_both_allowed_and_denied(self) -> None:
        assert not set(tools.ALLOWED_TOOLS.split(",")) & set(tools.DENIED_TOOLS.split(","))

    def test_the_allow_list_is_built_from_the_constants_the_note_is_built_from(self) -> None:
        allowed = set(tools.ALLOWED_TOOLS.split(","))
        expected = {f"Bash(git {verb}:*)" for verb in tools.ALLOWED_GIT_VERBS}
        expected |= {f"Bash({command}:*)" for command in tools.SHELL_COMMANDS}
        expected |= {f"Bash({python} -m {module}:*)" for python in tools.PYTHONS for module in tools.CHECK_MODULES}
        expected |= {
            f"Bash({python} -m scripts.forge {command}:*)"
            for python in tools.PYTHONS
            for command in tools.FORGE_COMMANDS
        }
        expected |= set(tools.FILE_TOOLS)

        assert expected <= allowed


class TestRestrictedShellNote:
    def test_it_names_every_command_the_allow_list_permits(self) -> None:
        note = tools.RESTRICTED_SHELL
        allowed_verbs = GIT_RULE.findall(tools.ALLOWED_TOOLS)

        assert allowed_verbs
        assert all(f"`{verb}`" in note or f"`git {verb}`" in note for verb in allowed_verbs)
        for name in (
            "Write",
            "Edit",
            "`ls`",
            "pytest",
            "`fix_checks`",
            "`run_checks`",
            "`run_suite`",
            "`forge check-body`",
        ):
            assert name in note

    def test_it_names_none_of_the_git_verbs_the_deny_list_blocks(self) -> None:
        denied_verbs = GIT_RULE.findall(tools.DENIED_TOOLS)

        assert denied_verbs
        assert not any(f"`{verb}`" in tools.RESTRICTED_SHELL for verb in denied_verbs)

    def test_it_follows_its_inputs(self) -> None:
        note = tools.restricted_shell(
            git_verbs=("add", "blame"),
            shell_commands=("ls", "cat"),
            check_modules=("scripts.run_checks",),
            forge_commands=(),
        )

        assert "`git add`, `blame`, `ls`, `cat`" in note
        assert "pytest and `run_checks`" in note
        assert "fix_checks" not in note and "check-body" not in note

    def test_it_keeps_the_advice_that_a_refusal_does_not_mean_the_shell_is_broken(self) -> None:
        assert "A refused command does not mean the shell is unusable" in tools.RESTRICTED_SHELL
        assert "do not write a question" in tools.RESTRICTED_SHELL
