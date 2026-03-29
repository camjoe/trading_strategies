from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from common.repo_paths import get_repo_root

from scripts.checks.mypy_check import run_mypy
from scripts.checks.pytest_check import run_pytest
from scripts.checks.readme_check import run_readme_consistency
from scripts.checks.shared import resolve_npm_exe, resolve_python_exe, run_step


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run fast day-to-day checks: README consistency, mypy, and pytest (optional frontend).",
    )
    parser.add_argument(
        "--readme-max-age-days",
        type=int,
        default=90,
        help="Max README age in days for advisory consistency check.",
    )
    parser.add_argument(
        "--with-frontend",
        action="store_true",
        help="Also run frontend lint/typecheck/tests.",
    )
    return parser.parse_args()


def _run_frontend_quick(frontend_dir: Path) -> None:
    npm_exe = resolve_npm_exe()
    run_step("Frontend quality: lint", [npm_exe, "run", "lint"], frontend_dir)
    run_step("Frontend quality: typecheck", [npm_exe, "run", "typecheck"], frontend_dir)
    run_step("Frontend tests: coverage", [npm_exe, "run", "test:coverage"], frontend_dir)


def run_quick(
    repo_root: Path,
    python_exe: str,
    readme_max_age_days: int = 90,
    with_frontend: bool = False,
) -> int:
    try:
        run_readme_consistency(
            repo_root=repo_root,
            max_age_days=readme_max_age_days,
        )
        run_mypy(repo_root=repo_root, python_exe=python_exe)
        run_pytest(repo_root=repo_root, python_exe=python_exe)

        if with_frontend:
            frontend_dir = repo_root / "paper_trading_ui" / "frontend"
            _run_frontend_quick(frontend_dir)
    except subprocess.CalledProcessError as exc:
        print(f"\nStep failed with exit code {exc.returncode}: {' '.join(exc.cmd)}")
        return exc.returncode

    print("\nQuick checks completed successfully.")
    return 0


def main() -> int:
    args = parse_args()
    repo_root = get_repo_root(__file__)
    python_exe = resolve_python_exe(repo_root)

    return run_quick(
        repo_root=repo_root,
        python_exe=python_exe,
        readme_max_age_days=args.readme_max_age_days,
        with_frontend=args.with_frontend,
    )


if __name__ == "__main__":
    raise SystemExit(main())
