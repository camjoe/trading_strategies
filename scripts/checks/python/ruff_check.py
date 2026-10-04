from __future__ import annotations

import argparse
from pathlib import Path

from common.git import get_repo_root
from scripts.checks._runner import resolve_python_exe, run_step

DEFAULT_TARGETS = ["src", "apps/paper_trading_web/backend", "scripts", "tests", "apps/trends"]


def run_ruff(repo_root: Path, python_exe: str, targets: list[str] | None = None) -> None:
    selected_targets = targets or DEFAULT_TARGETS
    run_step(
        "Python quality: ruff lint",
        [python_exe, "-m", "ruff", "check", *selected_targets],
        repo_root,
    )
    run_step(
        "Python quality: ruff format",
        [python_exe, "-m", "ruff", "format", "--check", *selected_targets],
        repo_root,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ruff lint and format checks.")
    parser.add_argument(
        "targets",
        nargs="*",
        help="Optional target paths. Defaults to all source directories.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    python_exe = resolve_python_exe(repo_root)
    run_ruff(repo_root=repo_root, python_exe=python_exe, targets=args.targets or None)
    print("\nRuff checks completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
