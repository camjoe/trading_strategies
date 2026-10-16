"""The ``claude`` CLI tool rules for an unattended agent, and the prompt note that describes them.

``ALLOWED_TOOLS`` and ``DENIED_TOOLS`` are comma-separated rule lists for ``--allowedTools`` and
``--disallowedTools``. ``RESTRICTED_SHELL`` names the same commands in the agent's prompt. All three are built from
the constants below.
"""

FILE_TOOLS = ("Write", "Edit")

ALLOWED_GIT_VERBS = ("add", "commit", "rm", "mv", "status", "diff", "log", "show")
DENIED_GIT_VERBS = ("push", "reset", "clean", "config", "update-ref", "checkout", "restore")
SHELL_COMMANDS = ("ls",)

PYTHONS = ("python", ".venv/bin/python", ".venv/Scripts/python.exe")
PYTEST_EXECUTABLES = (".venv/bin/pytest", ".venv/Scripts/pytest.exe")
CHECK_MODULES = ("scripts.fix_checks", "scripts.run_checks", "scripts.checks.run_suite")
FORGE_COMMANDS = ("check-body",)

# What the host runner and the container pass to `claude -p`: refuse a command outside the allow list instead of
# prompting for it, and ignore the repository's MCP servers.
DENY_BY_DEFAULT_OPTIONS = ("--permission-mode", "dontAsk", "--permission-prompts", "none", "--strict-mcp-config")


def _bash(rule: str) -> str:
    return f"Bash({rule}:*)"


def _and_list(items: list[str]) -> str:
    if len(items) < 3:
        return " and ".join(items)
    return ", ".join(items[:-1]) + ", and " + items[-1]


def _restricted_shell() -> str:
    commands = [
        f"`git {ALLOWED_GIT_VERBS[0]}`",
        *(f"`{verb}`" for verb in ALLOWED_GIT_VERBS[1:]),
        *(f"`{name}`" for name in SHELL_COMMANDS),
    ]
    checks = [
        "pytest",
        *(f"`{module.rsplit('.', 1)[-1]}`" for module in CHECK_MODULES),
        *(f"`forge {command}`" for command in FORGE_COMMANDS),
    ]
    return (
        f"Your shell is restricted: create and edit files with the {' and '.join(FILE_TOOLS)} tools, and run only "
        f"{', '.join(commands)}, and the repository's {_and_list(checks)}. A refused command does not mean the shell "
        "is unusable: use a file tool or one of those commands instead, and do not write a question for it."
    )


ALLOWED_TOOLS = ",".join(
    [
        "Read",
        "Glob",
        "Grep",
        *FILE_TOOLS,
        "Skill",
        "Agent",
        *(_bash(f"git {verb}") for verb in ALLOWED_GIT_VERBS),
        *(_bash(executable) for executable in PYTEST_EXECUTABLES),
        *(_bash(command) for command in SHELL_COMMANDS),
        *(
            _bash(f"{python} -m {module}")
            for python in PYTHONS
            for module in (*CHECK_MODULES, *(f"scripts.forge {command}" for command in FORGE_COMMANDS), "pytest")
        ),
    ]
)
# Claude Code applies an Edit path rule to the Write tool as well and never checks a Write path rule.
DENIED_TOOLS = ",".join(
    [
        *(_bash(f"git {verb}") for verb in DENIED_GIT_VERBS),
        _bash("gh"),
        "Edit(.git/**)",
    ]
)
RESTRICTED_SHELL = _restricted_shell()
