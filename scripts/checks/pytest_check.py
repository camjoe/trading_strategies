from __future__ import annotations

import argparse
from pathlib import Path

from common.repo_paths import get_repo_root

from scripts.checks.shared import resolve_python_exe, run_step


def run_pytest(repo_root: Path, python_exe: str, pytest_args: list[str] | None = None) -> None:
    command = [python_exe, "-m", "pytest", *(pytest_args or [])]
    run_step("Python tests: pytest", command, repo_root)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run pytest check as a standalone command.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to detected workspace root.",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Extra arguments passed through to pytest.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    python_exe = resolve_python_exe(repo_root)

    run_pytest(repo_root=repo_root, python_exe=python_exe, pytest_args=args.pytest_args)
    print("\nPytest check completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
