from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from common.git import get_repo_root

RISK_READ_ONLY = "read-only"
RISK_WRITES_LOCAL = "writes-local"
RISK_BROKER = "broker"
RISKS = frozenset({RISK_READ_ONLY, RISK_WRITES_LOCAL, RISK_BROKER})

KIND_CLI = "cli"
KIND_JOB = "job"
KIND_TOOL = "tool"

REPO_ROOT_PLACEHOLDER = "<repo-root>"
PYTHON_PLACEHOLDER = "<python>"

SCOPE_GLOBAL = "global"
SCOPE_COMMAND = "command"


class _ParserCaptured(Exception):
    def __init__(self, parser: argparse.ArgumentParser) -> None:
        super().__init__("parser captured")
        self.parser = parser


def capture_parser(entrypoint: Callable[[], object]) -> argparse.ArgumentParser:
    """Return the parser an entrypoint builds, without running its work.

    Every entrypoint parses its arguments before doing anything else, so a
    patched ``parse_args`` / ``parse_known_args`` that raises hands back the
    parser untouched.
    """

    def fake_parse_args(self: argparse.ArgumentParser, *_args: object, **_kwargs: object) -> None:
        raise _ParserCaptured(self)

    original_parse_args = argparse.ArgumentParser.parse_args
    original_parse_known_args = argparse.ArgumentParser.parse_known_args
    original_argv = sys.argv
    argparse.ArgumentParser.parse_args = fake_parse_args  # type: ignore[method-assign,assignment]
    argparse.ArgumentParser.parse_known_args = fake_parse_args  # type: ignore[method-assign,assignment]
    sys.argv = ["prog"]
    try:
        entrypoint()
    except _ParserCaptured as captured:
        return captured.parser
    finally:
        argparse.ArgumentParser.parse_args = original_parse_args  # type: ignore[method-assign]
        argparse.ArgumentParser.parse_known_args = original_parse_known_args  # type: ignore[method-assign]
        sys.argv = original_argv
    raise RuntimeError(f"{getattr(entrypoint, '__module__', entrypoint)}.main returned without parsing arguments")


def subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction[argparse.ArgumentParser] | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _spellings(*paths: str | Path | None) -> tuple[str, ...]:
    """Return each non-empty path in native and POSIX form; an empty one would match every string."""
    return tuple(dict.fromkeys(form for path in paths if path for form in (str(path), Path(path).as_posix())))


def _portable(text: str) -> str:
    """Replace the repo root and the interpreter path, which differ on every host.

    The interpreter goes first: it usually sits under the repo root.
    """
    prefix = Path(sys.prefix)
    for spelling in _spellings(sys.executable, prefix / "bin" / "python", prefix / "Scripts" / "python.exe"):
        text = text.replace(spelling, PYTHON_PLACEHOLDER)
    root = get_repo_root(__file__)
    for spelling in _spellings(root):
        text = text.replace(spelling, REPO_ROOT_PLACEHOLDER)
    if REPO_ROOT_PLACEHOLDER in text or PYTHON_PLACEHOLDER in text:
        return text.replace("\\", "/")
    return text


def _clean_text(text: str | None) -> str:
    return _portable(" ".join((text or "").split()))


def _json_safe(value: object) -> object:
    if isinstance(value, str):
        return _portable(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return _portable(str(value))


def _argument_kind(action: argparse.Action) -> str:
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        return "flag"
    if isinstance(action, argparse._AppendAction):
        return "repeatable"
    return "value"


def _type_name(action: argparse.Action) -> str:
    if _argument_kind(action) == "flag":
        return "flag"
    return getattr(action.type, "__name__", "str") if action.type is not None else "str"


def describe_argument(action: argparse.Action, scope: str = SCOPE_COMMAND) -> dict[str, Any]:
    positional = not action.option_strings
    return {
        "scope": scope,
        "flags": list(action.option_strings) or [action.dest],
        "dest": action.dest,
        "positional": positional,
        "kind": _argument_kind(action),
        "type": _type_name(action),
        "required": bool(action.required) or (positional and action.nargs not in ("?", "*", argparse.REMAINDER)),
        "default": _json_safe(action.default),
        "choices": _json_safe(list(action.choices)) if action.choices else None,
        "help": _clean_text(action.help),
    }


def describe_arguments(parser: argparse.ArgumentParser, scope: str = SCOPE_COMMAND) -> list[dict[str, Any]]:
    return [
        describe_argument(action, scope)
        for action in parser._actions
        if not isinstance(action, (argparse._HelpAction, argparse._SubParsersAction))
    ]


def _example_value(argument: dict[str, Any]) -> str:
    if argument["choices"]:
        return str(argument["choices"][0])
    return f"<{argument['dest'].upper()}>"


def _example_tokens(arguments: list[dict[str, Any]]) -> list[str]:
    tokens: list[str] = []
    for argument in arguments:
        if not argument["required"]:
            continue
        if argument["positional"]:
            tokens.append(_example_value(argument))
        elif argument["kind"] == "flag":
            tokens.append(argument["flags"][0])
        else:
            tokens.append(f"{argument['flags'][0]} {_example_value(argument)}")
    return tokens


def build_example(invocation: str, subcommand: str | None, arguments: list[dict[str, Any]]) -> str:
    """Write one example line: global options, then the subcommand, then its options."""
    global_arguments = [argument for argument in arguments if argument["scope"] == SCOPE_GLOBAL]
    command_arguments = [argument for argument in arguments if argument["scope"] != SCOPE_GLOBAL]
    parts = [invocation, *_example_tokens(global_arguments), *([subcommand] if subcommand else [])]
    return " ".join([*parts, *_example_tokens(command_arguments)])


def subcommand_helps(action: argparse._SubParsersAction[argparse.ArgumentParser]) -> dict[str, str]:
    return {choice.dest: _clean_text(choice.help) for choice in action._choices_actions}


def make_row(
    *,
    name: str,
    kind: str,
    group: str,
    risk: str,
    help_text: str,
    invocation: str,
    argv: list[str],
    subcommand: str | None,
    arguments: list[dict[str, Any]],
    module: str | None = None,
    schedule: str | None = None,
    runnable: bool = False,
) -> dict[str, Any]:
    if risk not in RISKS:
        raise ValueError(f"{name!r} has unknown risk {risk!r}")
    if not help_text:
        raise ValueError(f"{name!r} has no help text")
    if runnable and risk != RISK_READ_ONLY:
        raise ValueError(f"{name!r} is runnable but its risk is {risk!r}; only read-only entries may run")
    return {
        "name": name,
        "kind": kind,
        "group": group,
        "risk": risk,
        "module": module,
        "schedule": schedule,
        "runnable": runnable,
        "argv": argv,
        "subcommand": subcommand,
        "help": help_text,
        "example": build_example(invocation, subcommand, arguments),
        "arguments": arguments,
    }
