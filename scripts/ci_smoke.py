from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _run_step(name: str, command: list[str], cwd: Path) -> None:
    print(f"\n==> {name}")
    subprocess.run(command, cwd=str(cwd), check=True)


def _resolve_python_exe(repo_root: Path) -> str:
    candidates = [
        repo_root / ".venv" / "Scripts" / "python.exe",
        repo_root / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _resolve_npm_exe() -> str:
    candidates = ["npm"]
    if os.name == "nt":
        candidates = ["npm.cmd", "npm"]

    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    raise FileNotFoundError(
        "Unable to locate npm in PATH. Ensure Node.js is installed and npm is available in your shell."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local smoke checks that mirror core GitHub Actions workflows.",
    )
    parser.add_argument("--skip-python", action="store_true", help="Skip Python checks.")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip frontend checks.")
    parser.add_argument(
        "--skip-docs-freshness",
        action="store_true",
        help="Skip documentation freshness check.",
    )
    parser.add_argument(
        "--docs-base-ref",
        help="Optional base ref for docs freshness check (CI mode).",
    )
    parser.add_argument(
        "--docs-head-ref",
        default="HEAD",
        help="Optional head ref for docs freshness check when --docs-base-ref is set.",
    )
    parser.add_argument(
        "--install-python-tools",
        action="store_true",
        help="Install ruff and mypy before running quality gates.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    python_exe = _resolve_python_exe(repo_root)
    npm_exe = _resolve_npm_exe()

    try:
        if not args.skip_python:
            if not args.skip_docs_freshness:
                docs_cmd = [
                    python_exe,
                    "scripts/check_docs_freshness.py",
                    "--repo-root",
                    str(repo_root),
                ]
                if args.docs_base_ref:
                    docs_cmd.extend(["--base-ref", args.docs_base_ref, "--head-ref", args.docs_head_ref])
                _run_step(
                    "Python docs: freshness",
                    docs_cmd,
                    repo_root,
                )
            _run_step(
                "Python: upgrade pip",
                [python_exe, "-m", "pip", "install", "--upgrade", "pip"],
                repo_root,
            )
            _run_step(
                "Python: install requirements/dev.txt",
                [python_exe, "-m", "pip", "install", "-r", "requirements/dev.txt"],
                repo_root,
            )
            if args.install_python_tools:
                _run_step(
                    "Python: install quality tools",
                    [python_exe, "-m", "pip", "install", "ruff", "mypy"],
                    repo_root,
                )
            _run_step(
                "Python quality: ruff",
                [
                    python_exe,
                    "-m",
                    "ruff",
                    "check",
                    "trading",
                    "trends",
                    "paper_trading_ui/backend",
                    "--select",
                    "F,E9",
                ],
                repo_root,
            )
            _run_step(
                "Python quality: mypy",
                [
                    python_exe,
                    "-m",
                    "mypy",
                    "paper_trading_ui/backend",
                    "trading",
                    "--python-version",
                    "3.12",
                    "--ignore-missing-imports",
                    "--follow-imports=skip",
                ],
                repo_root,
            )
            _run_step("Python tests: pytest", [python_exe, "-m", "pytest"], repo_root)

        if not args.skip_frontend:
            frontend_dir = repo_root / "paper_trading_ui" / "frontend"
            _run_step("Frontend: npm ci", [npm_exe, "ci"], frontend_dir)
            _run_step("Frontend quality: lint", [npm_exe, "run", "lint"], frontend_dir)
            _run_step(
                "Frontend quality: typecheck",
                [npm_exe, "run", "typecheck"],
                frontend_dir,
            )
            _run_step(
                "Frontend tests: coverage",
                [npm_exe, "run", "test:coverage"],
                frontend_dir,
            )
    except subprocess.CalledProcessError as exc:
        print(f"\nStep failed with exit code {exc.returncode}: {' '.join(exc.cmd)}")
        return exc.returncode

    print("\nCI smoke checks completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
