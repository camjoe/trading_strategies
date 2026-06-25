from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from common.paths.repo_paths import get_repo_root

from scripts.checks.db_schema_check import run_db_schema_check
from scripts.checks.layer_check import run_layer_check
from scripts.checks.link_check import run_link_check
from scripts.checks.maps_check import run_maps_check
from scripts.checks.mypy_check import run_mypy
from scripts.checks.pytest_check import run_pytest
from scripts.checks.readme_check import run_readme_consistency
from scripts.checks.ruff_check import run_ruff
from scripts.documentation_ui.check import run_reference_docs_check
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
        "--skip-db-schema-check",
        action="store_true",
        help="Skip DB schema drift check.",
    )
    parser.add_argument(
        "--skip-maps-check",
        action="store_true",
        help="Skip maps drift check.",
    )
    parser.add_argument(
        "--skip-link-check",
        action="store_true",
        help="Skip doc link check.",
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
    parser.add_argument(
        "--with-reference-doc-checks",
        action="store_true",
        help="Also run all Financial & Market, Software, and API reference sync checks.",
    )
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
    skip_python: bool = False,
    skip_frontend: bool = False,
    skip_readme_consistency: bool = False,
    skip_db_schema_check: bool = False,
    skip_maps_check: bool = False,
    skip_link_check: bool = False,
    readme_max_age_days: int = 90,
    install_python_tools: bool = False,
    with_reference_doc_checks: bool = False,
) -> int:
    try:
        if not skip_python:
            if not skip_readme_consistency:
                run_readme_consistency(
                    repo_root=repo_root,
                    max_age_days=readme_max_age_days,
                    quiet=True,
                )
            if not skip_maps_check:
                run_maps_check(repo_root=repo_root, quiet=True)
            if not skip_db_schema_check:
                run_db_schema_check(repo_root=repo_root, quiet=True)
            if not skip_link_check:
                run_link_check(repo_root=repo_root, quiet=True)
            layer_exit = run_layer_check(repo_root=repo_root)
            if layer_exit != 0:
                return layer_exit
            if with_reference_doc_checks:
                reference_doc_exit = run_reference_docs_check(repo_root=repo_root)
                if reference_doc_exit != 0:
                    return reference_doc_exit
            run_step(
                "Python: upgrade pip",
                [python_exe, "-m", "pip", "install", "-q", "--upgrade", "pip"],
                repo_root,
            )
            run_step(
                "Python: install requirements-dev.txt",
                [python_exe, "-m", "pip", "install", "-q", "-r", "requirements-dev.txt"],
                repo_root,
            )
            if install_python_tools:
                run_step(
                    "Python: install quality tools",
                    [python_exe, "-m", "pip", "install", "-q", "ruff", "mypy"],
                    repo_root,
                )

            run_ruff(repo_root=repo_root, python_exe=python_exe)
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
        skip_db_schema_check=args.skip_db_schema_check,
        skip_maps_check=args.skip_maps_check,
        skip_link_check=args.skip_link_check,
        readme_max_age_days=args.readme_max_age_days,
        install_python_tools=args.install_python_tools,
        with_reference_doc_checks=args.with_reference_doc_checks,
    )


if __name__ == "__main__":
    raise SystemExit(main())
