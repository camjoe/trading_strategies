#!/usr/bin/env python3
"""Launch the paper trading backend and frontend together."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.ui_config import BACKEND_PORT, FRONTEND_PORT, UI_HOST


def npm_command() -> str:
    return "npm.cmd" if sys.platform.startswith("win") else "npm"


def build_commands() -> tuple[list[str], list[str]]:
    backend_command = [
        sys.executable,
        "-m",
        "uvicorn",
        "paper_trading_ui.backend.main:app",
        "--reload",
        "--host",
        UI_HOST,
        "--port",
        BACKEND_PORT,
    ]
    frontend_command = [
        npm_command(),
        "run",
        "dev",
        "--",
        "--host",
        UI_HOST,
        "--port",
        FRONTEND_PORT,
        "--strictPort",
    ]
    return backend_command, frontend_command


def _service_url(port: str) -> str:
    return f"http://{UI_HOST}:{port}"


def terminate_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _terminate_processes(*processes: subprocess.Popen[str]) -> None:
    for process in processes:
        terminate_process(process)


def _exit_code_or_zero(*exit_codes: int | None) -> int:
    for exit_code in exit_codes:
        if exit_code is not None:
            return exit_code
    return 0


def main() -> int:
    scripts_dir = Path(__file__).resolve().parent
    repo_root = scripts_dir.parent
    ui_dir = repo_root / "paper_trading_ui"
    backend_command, frontend_command = build_commands()
    env = {
        **os.environ,
        "VITE_API_BASE": _service_url(BACKEND_PORT),
    }

    if shutil.which(frontend_command[0]) is None:
        print("Error: npm was not found in PATH.", file=sys.stderr)
        return 1

    backend_proc = subprocess.Popen(
        backend_command,
        cwd=repo_root,
        env=env,
    )
    frontend_proc = subprocess.Popen(
        frontend_command,
        cwd=ui_dir / "frontend",
        env=env,
    )

    print("Launched backend and frontend.")
    print(f"Backend:  {_service_url(BACKEND_PORT)}")
    print(f"Frontend: {_service_url(FRONTEND_PORT)}")
    print("Press Ctrl+C to stop both services.")

    stop_requested = False

    def handle_signal(signum: int, _frame: object) -> None:
        nonlocal stop_requested
        if stop_requested:
            return
        stop_requested = True
        print(f"\nReceived signal {signum}, stopping services...")
        _terminate_processes(backend_proc, frontend_proc)

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)

    try:
        while True:
            backend_exit = backend_proc.poll()
            frontend_exit = frontend_proc.poll()

            if backend_exit is not None or frontend_exit is not None:
                if backend_exit is not None and frontend_exit is None:
                    print("Backend exited, stopping frontend...")
                    terminate_process(frontend_proc)
                    return backend_exit
                if frontend_exit is not None and backend_exit is None:
                    print("Frontend exited, stopping backend...")
                    terminate_process(backend_proc)
                    return frontend_exit
                return _exit_code_or_zero(backend_exit, frontend_exit)

            time.sleep(0.2)
    finally:
        _terminate_processes(backend_proc, frontend_proc)


if __name__ == "__main__":
    raise SystemExit(main())
