from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from common.paths.executables import resolve_repo_python_exe


@dataclass(frozen=True)
class CheckStep:
    name: str
    run: Callable[[], int | None]
    skip: bool = False


def run_check_steps(steps: list[CheckStep]) -> int:
    for step in steps:
        if step.skip:
            print(f"\nSKIP: {step.name}")
            continue
        exit_code = step.run() or 0
        if exit_code != 0:
            return exit_code
    return 0


def run_step(name: str, command: list[str], cwd: Path) -> None:
    print(f"\n==> {name}")
    subprocess.run(command, cwd=str(cwd), check=True)


def resolve_python_exe(repo_root: Path) -> str:
    return resolve_repo_python_exe(repo_root)


def resolve_npm_exe() -> str:
    candidates = ["npm"]
    if os.name == "nt":
        candidates = ["npm.cmd", "npm"]

    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    raise FileNotFoundError(
        "Unable to locate npm in PATH. Ensure Node.js is installed and npm is available in your shell.",
    )
