"""Run one read-only catalog entry as a subprocess.

The generated catalog decides what may run: an entry runs only when it is marked
``runnable``. This module turns validated form values into an argument list, runs
it without a shell, and shapes the result. It holds no policy of its own.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from trading.domain.exceptions import NotFoundError, ValidationError

from ..config import COMMANDS_REGISTRY_PATH, ROOT_DIR

RUN_TIMEOUT_SECONDS = 60
MAX_OUTPUT_CHARS = 200_000

_run_lock = threading.Lock()


def load_catalog(path: Path = COMMANDS_REGISTRY_PATH) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(entry["name"]): entry for entry in payload["commands"]}


def _is_missing(value: object) -> bool:
    return value is None or value == "" or value is False or value == []


def _coerce_text(argument: dict[str, Any], value: object) -> str:
    dest = argument["dest"]
    if isinstance(value, (dict, list, bool)):
        raise ValidationError(f"{dest} must be a single value")
    text = str(value).strip()
    if "\n" in text or "\r" in text or "\x00" in text:
        raise ValidationError(f"{dest} must be one line of text")
    try:
        if argument["type"] == "int":
            int(text)
        elif argument["type"] == "float":
            float(text)
    except ValueError as exc:
        raise ValidationError(f"{dest} must be a {argument['type']}") from exc
    choices = argument["choices"]
    if choices and text not in [str(choice) for choice in choices]:
        raise ValidationError(f"{dest} must be one of: {', '.join(str(choice) for choice in choices)}")
    return text


def build_arguments(entry: dict[str, Any], values: dict[str, Any]) -> list[str]:
    """Return the command-line arguments for ``entry``, or raise ValidationError.

    Options are written as ``--flag=value`` so a value can never be read as another
    option. Positional values that start with ``-`` are rejected for the same reason.
    """
    known = {argument["dest"] for argument in entry["arguments"]}
    unknown = sorted(set(values) - known)
    if unknown:
        raise ValidationError(f"Unknown arguments for {entry['name']}: {', '.join(unknown)}")

    options: list[str] = []
    positionals: list[str] = []
    for argument in entry["arguments"]:
        dest = argument["dest"]
        value = values.get(dest)
        if _is_missing(value):
            if argument["required"]:
                raise ValidationError(f"{dest} is required")
            continue
        flag = argument["flags"][0]
        if argument["kind"] == "flag":
            if value is not True:
                raise ValidationError(f"{dest} must be true or false")
            options.append(flag)
        elif argument["kind"] == "repeatable":
            items = value if isinstance(value, list) else [value]
            options.extend(f"{flag}={_coerce_text(argument, item)}" for item in items)
        elif argument["positional"]:
            text = _coerce_text(argument, value)
            if text.startswith("-"):
                raise ValidationError(f"{dest} must not start with '-'")
            positionals.append(text)
        else:
            options.append(f"{flag}={_coerce_text(argument, value)}")
    return [*options, *positionals]


def _display_command(argv: list[str]) -> str:
    return " ".join(["python", *(shlex.quote(part) for part in argv)])


def _child_environment() -> dict[str, str]:
    return {**os.environ, "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1", "NO_COLOR": "1"}


def _decode(output: bytes | str | None) -> str:
    if output is None:
        return ""
    return output if isinstance(output, str) else output.decode("utf-8", errors="replace")


def run_entry(
    name: str,
    values: dict[str, Any],
    *,
    catalog: dict[str, dict[str, Any]] | None = None,
    timeout_seconds: int = RUN_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    entries = load_catalog() if catalog is None else catalog
    entry = entries.get(name)
    if entry is None:
        raise NotFoundError(f"No catalog entry named {name!r}")
    if not entry.get("runnable"):
        raise ValidationError(f"{name} cannot be run from the UI; run it from a terminal")

    argv = [*entry["argv"], *build_arguments(entry, values)]
    if not _run_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Another command is already running")
    try:
        started = time.monotonic()
        timed_out = False
        try:
            completed = subprocess.run(  # noqa: S603 - fixed interpreter, validated argv, no shell
                [sys.executable, *argv],
                cwd=ROOT_DIR,
                env=_child_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                check=False,
            )
            exit_code: int | None = completed.returncode
            output = _decode(completed.stdout)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = None
            output = _decode(exc.stdout)
        duration = time.monotonic() - started
    finally:
        _run_lock.release()

    truncated = len(output) > MAX_OUTPUT_CHARS
    return {
        "name": name,
        "command": _display_command(argv),
        "exitCode": exit_code,
        "timedOut": timed_out,
        "truncated": truncated,
        "durationSeconds": round(duration, 2),
        "output": output[:MAX_OUTPUT_CHARS],
    }
