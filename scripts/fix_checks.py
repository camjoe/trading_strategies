from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from common.paths.repo_paths import get_repo_root

from scripts.checks.ruff_check import DEFAULT_TARGETS
from scripts.checks.shared import resolve_python_exe, run_step


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply deterministic, behavior-preserving fixes for local check drift.",
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help="Optional Python target paths. Defaults to the same targets as the Ruff check gate.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root.")
    parser.add_argument(
        "--skip-ruff-fix",
        action="store_true",
        help="Skip `ruff check --fix`.",
    )
    parser.add_argument(
        "--skip-format",
        action="store_true",
        help="Skip `ruff format`.",
    )
    return parser.parse_args()


def run_fix_checks(
    repo_root: Path,
    python_exe: str,
    targets: list[str] | None = None,
    skip_ruff_fix: bool = False,
    skip_format: bool = False,
) -> int:
    selected_targets = targets or DEFAULT_TARGETS
    try:
        if not skip_ruff_fix:
            run_step(
                "Python auto-fix: ruff check --fix",
                [python_exe, "-m", "ruff", "check", "--fix", *selected_targets],
                repo_root,
            )
        if not skip_format:
            run_step(
                "Python auto-fix: ruff format",
                [python_exe, "-m", "ruff", "format", *selected_targets],
                repo_root,
            )
    except subprocess.CalledProcessError as exc:
        print(f"\nStep failed with exit code {exc.returncode}: {' '.join(exc.cmd)}")
        return exc.returncode

    print("\nDeterministic fixes completed successfully.")
    return 0


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    python_exe = resolve_python_exe(repo_root)
    return run_fix_checks(
        repo_root=repo_root,
        python_exe=python_exe,
        targets=args.targets or None,
        skip_ruff_fix=args.skip_ruff_fix,
        skip_format=args.skip_format,
    )


if __name__ == "__main__":
    raise SystemExit(main())
