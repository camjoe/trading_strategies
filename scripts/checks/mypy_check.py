from __future__ import annotations

import argparse
from pathlib import Path

from common.repo_paths import get_repo_root

from scripts.checks.shared import resolve_python_exe, run_step


DEFAULT_TARGETS = ["paper_trading_ui/backend", "trading"]


def run_mypy(
    repo_root: Path,
    python_exe: str,
    targets: list[str] | None = None,
    python_version: str = "3.12",
    ignore_missing_imports: bool = True,
    follow_imports_skip: bool = True,
) -> None:
    selected_targets = targets or DEFAULT_TARGETS
    command = [
        python_exe,
        "-m",
        "mypy",
        *selected_targets,
        "--python-version",
        python_version,
    ]
    if ignore_missing_imports:
        command.append("--ignore-missing-imports")
    if follow_imports_skip:
        command.append("--follow-imports=skip")

    run_step("Python quality: mypy", command, repo_root)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run mypy check for default or custom Python target paths.",
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help="Optional mypy target paths. Defaults to backend and trading modules.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to detected workspace root.",
    )
    parser.add_argument(
        "--python-version",
        default="3.12",
        help="Python version passed to mypy.",
    )
    parser.add_argument(
        "--no-ignore-missing-imports",
        action="store_true",
        help="Disable --ignore-missing-imports.",
    )
    parser.add_argument(
        "--no-follow-imports-skip",
        action="store_true",
        help="Disable --follow-imports=skip.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    python_exe = resolve_python_exe(repo_root)

    run_mypy(
        repo_root=repo_root,
        python_exe=python_exe,
        targets=args.targets or None,
        python_version=args.python_version,
        ignore_missing_imports=not args.no_ignore_missing_imports,
        follow_imports_skip=not args.no_follow_imports_skip,
    )
    print("\nMypy check completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
