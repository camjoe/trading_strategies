from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def run_step(name: str, command: list[str], cwd: Path) -> None:
    print(f"\n==> {name}")
    subprocess.run(command, cwd=str(cwd), check=True)


def resolve_python_exe(repo_root: Path) -> str:
    candidates = [
        repo_root / ".venv" / "Scripts" / "python.exe",
        repo_root / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


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
