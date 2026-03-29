from __future__ import annotations

import argparse

from common.repo_paths import get_repo_root

from scripts.checks.ci import run_ci
from scripts.checks.quick import run_quick
from scripts.checks.shared import resolve_python_exe


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Unified check runner. Use --profile quick for day-to-day checks "
            "or --profile ci for CI-shaped smoke validation."
        ),
    )
    parser.add_argument(
        "--profile",
        choices=("quick", "ci"),
        default="quick",
        help="Check profile to run.",
    )
    parser.add_argument(
        "--readme-max-age-days",
        type=int,
        default=90,
        help="Max README age in days for consistency checks.",
    )

    # Quick profile option
    parser.add_argument(
        "--with-frontend",
        action="store_true",
        help="Quick profile: also run frontend lint/typecheck/tests.",
    )

    # CI profile options
    parser.add_argument("--skip-python", action="store_true", help="CI profile: skip Python checks.")
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="CI profile: skip frontend checks.",
    )
    parser.add_argument(
        "--skip-readme-consistency",
        action="store_true",
        help="CI profile: skip README consistency check.",
    )
    parser.add_argument(
        "--install-python-tools",
        action="store_true",
        help="CI profile: install ruff and mypy before quality gates.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = get_repo_root(__file__)
    python_exe = resolve_python_exe(repo_root)

    if args.profile == "quick":
        return run_quick(
            repo_root=repo_root,
            python_exe=python_exe,
            readme_max_age_days=args.readme_max_age_days,
            with_frontend=args.with_frontend,
        )

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
