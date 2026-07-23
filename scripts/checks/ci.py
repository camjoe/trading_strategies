from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from common.paths.repo_paths import get_repo_root
from scripts.checks._runner import CheckStep, resolve_npm_exe, resolve_python_exe, run_check_steps, run_step
from scripts.checks.docs.docs_check import run_docs_check
from scripts.checks.python.python_check import run_python_check
from scripts.checks.repo.repo_check import run_repo_check


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local smoke checks that mirror core GitHub Actions workflows.",
    )
    parser.add_argument(
        "--readme-max-age-days",
        type=int,
        default=90,
        help="Max README age in days for advisory consistency check.",
    )
    parser.add_argument("--skip-frontend", action="store_true", help="Skip frontend checks.")
    return parser.parse_args()


def _run_frontend_ci(repo_root: Path) -> None:
    npm_exe = resolve_npm_exe()
    frontend_dir = repo_root / "apps" / "paper_trading_web" / "frontend"
    run_step("Frontend: npm ci", [npm_exe, "ci"], frontend_dir)
    run_step("Frontend quality: lint", [npm_exe, "run", "lint"], frontend_dir)
    run_step("Frontend quality: typecheck", [npm_exe, "run", "typecheck"], frontend_dir)
    run_step("Frontend tests: coverage", [npm_exe, "run", "test:coverage"], frontend_dir)


def run_ci(
    repo_root: Path,
    python_exe: str,
    skip_frontend: bool = False,
    readme_max_age_days: int = 90,
) -> int:
    try:
        check_exit = run_check_steps(
            [
                CheckStep(
                    "Documentation checks",
                    lambda: run_docs_check(
                        repo_root=repo_root,
                        enforce=True,
                        quiet=True,
                        readme_max_age_days=readme_max_age_days,
                    ),
                ),
                CheckStep("Repository checks", lambda: run_repo_check(repo_root=repo_root)),
                CheckStep("Python checks", lambda: run_python_check(repo_root=repo_root, python_exe=python_exe)),
            ]
        )
        if check_exit != 0:
            return check_exit

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
        skip_frontend=args.skip_frontend,
        readme_max_age_days=args.readme_max_age_days,
    )


if __name__ == "__main__":
    raise SystemExit(main())
