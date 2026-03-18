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

HOST = "127.0.0.1"
API_PORT = "8000"
FRONTEND_PORT = "5173"


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
        HOST,
        "--port",
        API_PORT,
    ]
    frontend_command = [
        npm_command(),
        "run",
        "dev",
        "--",
        "--host",
        HOST,
        "--port",
        FRONTEND_PORT,
        "--strictPort",
    ]
    return backend_command, frontend_command


def terminate_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> int:
    scripts_dir = Path(__file__).resolve().parent
    repo_root = scripts_dir.parent
    ui_dir = repo_root / "paper_trading_ui"
    backend_command, frontend_command = build_commands()
    env = {
        **os.environ,
        "VITE_API_BASE": f"http://{HOST}:{API_PORT}",
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
    print(f"Backend:  http://{HOST}:{API_PORT}")
    print(f"Frontend: http://{HOST}:{FRONTEND_PORT}")
    print("Press Ctrl+C to stop both services.")

    stop_requested = False

    def handle_signal(signum: int, _frame: object) -> None:
        nonlocal stop_requested
        if stop_requested:
            return
        stop_requested = True
        print(f"\nReceived signal {signum}, stopping services...")
        terminate_process(backend_proc)
        terminate_process(frontend_proc)

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
                return backend_exit if backend_exit is not None else frontend_exit or 0

            time.sleep(0.2)
    finally:
        terminate_process(backend_proc)
        terminate_process(frontend_proc)


if __name__ == "__main__":
    raise SystemExit(main())
