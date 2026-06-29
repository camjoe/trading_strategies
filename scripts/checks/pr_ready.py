"""Deterministic PR readiness gate.

Runs all non-AI checks in fail-fast order before submitting a pull request:

    1. Layer boundary check
    2. Ruff lint + format
    3. Mypy type check
    4. Tests scoped to branch changes (vs a base ref)

Each step is independently skippable via flags.  This script is intentionally
AI-free — it is the fast, repeatable part of the PR readiness workflow.  The
AI steps (code review, architecture review, readiness report) are handled by
the ``pr-readiness`` Copilot skill.

Usage::

    # Full run vs develop (default)
    python -m scripts.checks.pr_ready

    # Custom base branch
    python -m scripts.checks.pr_ready --base main

    # Skip individual steps
    python -m scripts.checks.pr_ready --skip-layer
    python -m scripts.checks.pr_ready --skip-lint
    python -m scripts.checks.pr_ready --skip-tests

    # Fast iteration without coverage overhead
    python -m scripts.checks.pr_ready --no-cov
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from common.paths.repo_paths import get_repo_root

from scripts.checks.layer_check import run_layer_check
from scripts.checks.mypy_check import run_mypy
from scripts.checks.ruff_check import run_ruff
from scripts.checks.run_suite import detect_suites_from_changes, run_suite
from scripts.checks.shared import resolve_python_exe

_SEPARATOR = "-" * 60


def _header(step: int, label: str) -> None:
    print(f"\n{_SEPARATOR}")
    print(f"  Step {step}: {label}")
    print(_SEPARATOR)


def _pass(label: str) -> None:
    print(f"\n[PASS] {label} passed.")


def _fail(label: str, hint: str = "") -> None:
    print(f"\n[FAIL] {label} FAILED.", file=sys.stderr)
    if hint:
        print(f"       {hint}", file=sys.stderr)


def _skip(label: str) -> None:
    print(f"\n[SKIP] {label} (--skip flag).")


def run_pr_ready(
    repo_root: Path,
    python_exe: str,
    base_ref: str = "develop",
    skip_layer: bool = False,
    skip_lint: bool = False,
    skip_tests: bool = False,
    no_cov: bool = False,
) -> int:
    """Run all deterministic PR readiness checks. Returns 0 on full pass, 1 on any failure."""
    failed_steps: list[str] = []

    # ── Step 1: Layer boundary check ─────────────────────────────────────────
    _header(1, "Layer boundary check")
    if skip_layer:
        _skip("Layer check")
    else:
        exit_code = run_layer_check(repo_root=repo_root)
        if exit_code != 0:
            _fail("Layer check", "Fix import boundary violations above, then re-run.")
            failed_steps.append("Layer boundary check")
            return _report_failure(failed_steps)

        _pass("Layer check")

    # ── Step 2: Ruff + mypy ──────────────────────────────────────────────────
    _header(2, "Linting (ruff + mypy)")
    if skip_lint:
        _skip("Lint")
    else:
        try:
            run_ruff(repo_root=repo_root, python_exe=python_exe)
            run_mypy(repo_root=repo_root, python_exe=python_exe)
        except subprocess.CalledProcessError as exc:
            _fail("Lint", f"Exit code {exc.returncode}. Fix linting errors above, then re-run.")
            failed_steps.append("Linting (ruff + mypy)")
            return _report_failure(failed_steps)

        _pass("Lint")

    # ── Step 3: Branch-targeted tests ────────────────────────────────────────
    _header(3, f"Tests (branch changes vs {base_ref!r})")
    if skip_tests:
        _skip("Tests")
    else:
        tests_root = repo_root / "tests"
        suites = detect_suites_from_changes(repo_root, tests_root, base_ref=base_ref)

        if not suites:
            print(f"\n[SKIP] No changed test suites detected vs {base_ref!r} — skipping.")
        else:
            print(f"    Suites: {', '.join(suites)}")
            extra_args = ["--override-ini", "addopts=-q -n auto"]
            if no_cov:
                extra_args += ["--no-cov"]
            exit_code = run_suite(
                suite_names=suites,
                repo_root=repo_root,
                python_exe=python_exe,
                extra_args=extra_args,
            )
            if exit_code != 0:
                _fail("Tests", "Fix failing tests above, then re-run.")
                failed_steps.append(f"Tests (vs {base_ref!r})")
                return _report_failure(failed_steps)

            _pass("Tests")

    # ── All deterministic checks passed ──────────────────────────────────────
    print(f"\n{_SEPARATOR}")
    print("  [PASS] All deterministic checks passed.")
    print(_SEPARATOR)
    print()
    print("  Next: run the AI review steps via Copilot CLI:")
    print(f"    pr ready: {base_ref}   -- full workflow (code review + arch review + report)")
    print("    pr code review          -- code quality and style review only")
    print("    pr arch review          -- architecture and coupling review only")
    print()
    return 0


def _report_failure(failed_steps: list[str]) -> int:
    print(f"\n{_SEPARATOR}", file=sys.stderr)
    print("  [FAIL] PR readiness gate FAILED.", file=sys.stderr)
    for step in failed_steps:
        print(f"         - {step}", file=sys.stderr)
    print(_SEPARATOR, file=sys.stderr)
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministic PR readiness gate.\n\n"
            "Runs layer check -> ruff + mypy -> branch-targeted tests in fail-fast order.\n"
            "Use 'pr ready' in Copilot CLI for the full workflow including AI review steps."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m scripts.checks.pr_ready\n"
            "  python -m scripts.checks.pr_ready --base main\n"
            "  python -m scripts.checks.pr_ready --skip-tests\n"
            "  python -m scripts.checks.pr_ready --no-cov\n"
        ),
        # ASCII-safe output for Windows consoles
    )
    parser.add_argument(
        "--base",
        metavar="REF",
        default="develop",
        help="Base branch or git ref for test targeting and diff scope. Default: develop.",
    )
    parser.add_argument(
        "--skip-layer",
        action="store_true",
        help="Skip the layer boundary check.",
    )
    parser.add_argument(
        "--skip-lint",
        action="store_true",
        help="Skip ruff and mypy.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip branch-targeted pytest run.",
    )
    parser.add_argument(
        "--no-cov",
        action="store_true",
        help="Run tests without coverage (faster).",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to auto-detected workspace root.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    python_exe = resolve_python_exe(repo_root)

    return run_pr_ready(
        repo_root=repo_root,
        python_exe=python_exe,
        base_ref=args.base,
        skip_layer=args.skip_layer,
        skip_lint=args.skip_lint,
        skip_tests=args.skip_tests,
        no_cov=args.no_cov,
    )


if __name__ == "__main__":
    raise SystemExit(main())
