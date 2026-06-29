from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from common.paths.executables import resolve_repo_python_exe


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
