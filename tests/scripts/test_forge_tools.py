import re

from scripts.forge import tools

# The verb in a `Bash(git <verb>:*)` tool rule.
GIT_RULE = re.compile(r"Bash\(git (\w+):\*\)")

EXPECTED_ALLOWED = [
    "Read",
    "Glob",
    "Grep",
    "Write",
    "Edit",
    "Skill",
    "Agent",
    "Bash(git add:*)",
    "Bash(git commit:*)",
    "Bash(git rm:*)",
    "Bash(git mv:*)",
    "Bash(git status:*)",
    "Bash(git diff:*)",
    "Bash(git log:*)",
    "Bash(git show:*)",
    "Bash(.venv/bin/pytest:*)",
    "Bash(.venv/Scripts/pytest.exe:*)",
    "Bash(ls:*)",
    *(
        f"Bash({python} -m {module}:*)"
        for python in ("python", ".venv/bin/python", ".venv/Scripts/python.exe")
        for module in (
            "scripts.fix_checks",
            "scripts.run_checks",
            "scripts.checks.run_suite",
            "scripts.forge check-body",
            "pytest",
        )
    ),
]
EXPECTED_DENIED = [
    "Bash(git push:*)",
    "Bash(git reset:*)",
    "Bash(git clean:*)",
    "Bash(git config:*)",
    "Bash(git update-ref:*)",
    "Bash(git checkout:*)",
    "Bash(git restore:*)",
    "Bash(gh:*)",
    "Edit(.git/**)",
]

EXPECTED_NOTE = (
    "Your shell is restricted: create and edit files with the Write and Edit tools, and run only `git add`, `commit`, "
    "`rm`, `mv`, `status`, `diff`, `log`, `show`, `ls`, and the repository's pytest, `fix_checks`, `run_checks`, "
    "`run_suite`, and `forge check-body`. A refused command does not mean the shell is unusable: use a file tool or "
    "one of those commands instead, and do not write a question for it."
)


class TestToolLimits:
    def test_the_agent_may_use_exactly_these_tools(self) -> None:
        assert tools.ALLOWED_TOOLS.split(",") == EXPECTED_ALLOWED
        assert tools.DENIED_TOOLS.split(",") == EXPECTED_DENIED

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

        for item in ("Edit(.git/**)", "Bash(gh:*)", "Bash(git push:*)", "Bash(git config:*)"):
            assert item in denied

    def test_the_edit_rule_alone_denies_writes_into_git(self) -> None:
        """Claude Code applies an Edit path rule to the Write tool and never checks a Write path rule.

        Checked on the CLI in `docs/reference/agent-sandbox.md`, so there is deliberately no `Write(.git/**)` entry.
        """
        assert "Write(.git/**)" not in tools.DENIED_TOOLS.split(",")

    def test_nothing_is_both_allowed_and_denied(self) -> None:
        assert not set(tools.ALLOWED_TOOLS.split(",")) & set(tools.DENIED_TOOLS.split(","))


class TestRestrictedShellNote:
    def test_it_reads_exactly_like_this(self) -> None:
        assert tools.RESTRICTED_SHELL == EXPECTED_NOTE

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

    def test_a_list_reads_naturally_with_one_two_or_three_items(self) -> None:
        assert tools._and_list(["a"]) == "a"
        assert tools._and_list(["a", "b"]) == "a and b"
        assert tools._and_list(["a", "b", "c"]) == "a, b, and c"
