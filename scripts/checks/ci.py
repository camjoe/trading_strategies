from __future__ import annotations

import argparse
import subprocess

from common.repo_paths import get_repo_root

from scripts.checks.mypy_check import run_mypy
from scripts.checks.pytest_check import run_pytest
from scripts.checks.readme_check import run_readme_consistency
from scripts.checks.shared import resolve_npm_exe, resolve_python_exe, run_step


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local smoke checks that mirror core GitHub Actions workflows.",
    )
    parser.add_argument("--skip-python", action="store_true", help="Skip Python checks.")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip frontend checks.")
    parser.add_argument(
        "--skip-readme-consistency",
        action="store_true",
        help="Skip README consistency check.",
    )
    parser.add_argument(
        "--readme-max-age-days",
        type=int,
        default=90,
        help="Max README age in days for advisory consistency check.",
    )
    parser.add_argument(
        "--install-python-tools",
        action="store_true",
        help="Install ruff and mypy before running quality gates.",
    )
    return parser.parse_args()


def _run_ruff(repo_root, python_exe: str) -> None:
    run_step(
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


def _run_frontend_ci(repo_root) -> None:
    npm_exe = resolve_npm_exe()
    frontend_dir = repo_root / "paper_trading_ui" / "frontend"
    run_step("Frontend: npm ci", [npm_exe, "ci"], frontend_dir)
    run_step("Frontend quality: lint", [npm_exe, "run", "lint"], frontend_dir)
    run_step("Frontend quality: typecheck", [npm_exe, "run", "typecheck"], frontend_dir)
    run_step("Frontend tests: coverage", [npm_exe, "run", "test:coverage"], frontend_dir)


def run_ci(
    repo_root,
    python_exe: str,
    skip_python: bool = False,
    skip_frontend: bool = False,
    skip_readme_consistency: bool = False,
    readme_max_age_days: int = 90,
    install_python_tools: bool = False,
) -> int:
    try:
        if not skip_python:
            if not skip_readme_consistency:
                run_readme_consistency(
                    repo_root=repo_root,
                    max_age_days=readme_max_age_days,
                )
            run_step(
                "Python: upgrade pip",
                [python_exe, "-m", "pip", "install", "--upgrade", "pip"],
                repo_root,
            )
            run_step(
                "Python: install requirements/dev.txt",
                [python_exe, "-m", "pip", "install", "-r", "requirements/dev.txt"],
                repo_root,
            )
            if install_python_tools:
                run_step(
                    "Python: install quality tools",
                    [python_exe, "-m", "pip", "install", "ruff", "mypy"],
                    repo_root,
                )

            _run_ruff(repo_root, python_exe)
            run_mypy(repo_root=repo_root, python_exe=python_exe)
            run_pytest(repo_root=repo_root, python_exe=python_exe)

        if not skip_frontend:
            _run_frontend_ci(repo_root)
    except subprocess.CalledProcessError as exc:
        print(f"\nStep failed with exit code {exc.returncode}: {' '.join(exc.cmd)}")
        return exc.returncode

    print("\nCI smoke checks completed successfully.")
    return 0


def main() -> int:
    args = parse_args()
    repo_root = get_repo_root(__file__)
    python_exe = resolve_python_exe(repo_root)

    return run_ci(
        repo_root=repo_root,
        python_exe=python_exe,
        skip_python=args.skip_python,
        skip_frontend=args.skip_frontend,
        skip_readme_consistency=args.skip_readme_consistency,
        readme_max_age_days=args.readme_max_age_days,
        install_python_tools=args.install_python_tools,
    )


if __name__ == "__main__":
    raise SystemExit(main())
