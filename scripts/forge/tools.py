"""What an unattended agent may run, and the prompt note that says so, built from one set of constants.

``ALLOWED_TOOLS`` and ``DENIED_TOOLS`` are the ``claude`` CLI's tool rules, as comma-separated lists.
``RESTRICTED_SHELL`` is the note in the agent's prompt. Both come from the constants below, so a command added to
or removed from one place changes the rules and the note together.
"""

READ_TOOLS = ("Read", "Glob", "Grep")
FILE_TOOLS = ("Write", "Edit")
OTHER_TOOLS = ("Skill", "Agent")

ALLOWED_GIT_VERBS = ("add", "commit", "rm", "mv", "status", "diff", "log", "show")
DENIED_GIT_VERBS = ("push", "reset", "clean", "config", "update-ref", "checkout", "restore")
SHELL_COMMANDS = ("ls",)

PYTHONS = ("python", ".venv/bin/python", ".venv/Scripts/python.exe")
PYTEST_EXECUTABLES = (".venv/bin/pytest", ".venv/Scripts/pytest.exe")
CHECK_MODULES = ("scripts.fix_checks", "scripts.run_checks", "scripts.checks.run_suite")
FORGE_COMMANDS = ("check-body",)


def _bash(rule: str) -> str:
    return f"Bash({rule}:*)"


def _python_modules() -> list[str]:
    """Each module an agent may start with ``python -m``: the checks, the forge commands, and pytest."""
    return [*CHECK_MODULES, *(f"scripts.forge {command}" for command in FORGE_COMMANDS), "pytest"]


def _and_list(items: list[str]) -> str:
    if len(items) < 3:
        return " and ".join(items)
    return ", ".join(items[:-1]) + ", and " + items[-1]


def restricted_shell(
    git_verbs: tuple[str, ...] = ALLOWED_GIT_VERBS,
    shell_commands: tuple[str, ...] = SHELL_COMMANDS,
    check_modules: tuple[str, ...] = CHECK_MODULES,
    forge_commands: tuple[str, ...] = FORGE_COMMANDS,
) -> str:
    """The prompt note naming the tools and commands the agent has, in the words the agent needs to avoid a refusal."""
    commands = [
        f"`git {git_verbs[0]}`",
        *(f"`{verb}`" for verb in git_verbs[1:]),
        *(f"`{name}`" for name in shell_commands),
    ]
    checks = [
        "pytest",
        *(f"`{module.rsplit('.', 1)[-1]}`" for module in check_modules),
        *(f"`forge {command}`" for command in forge_commands),
    ]
    return (
        f"Your shell is restricted: create and edit files with the {' and '.join(FILE_TOOLS)} tools, and run only "
        f"{', '.join(commands)}, and the repository's {_and_list(checks)}. A refused command does not mean the shell "
        "is unusable: use a file tool or one of those commands instead, and do not write a question for it."
    )


ALLOWED_TOOLS = ",".join(
    [
        *READ_TOOLS,
        *FILE_TOOLS,
        *OTHER_TOOLS,
        *(_bash(f"git {verb}") for verb in ALLOWED_GIT_VERBS),
        *(_bash(executable) for executable in PYTEST_EXECUTABLES),
        *(_bash(command) for command in SHELL_COMMANDS),
        *(_bash(f"{python} -m {module}") for python in PYTHONS for module in _python_modules()),
    ]
)
DENIED_TOOLS = ",".join(
    [
        *(_bash(f"git {verb}") for verb in DENIED_GIT_VERBS),
        _bash("gh"),
        "Edit(.git/**)",
    ]
)
RESTRICTED_SHELL = restricted_shell()
