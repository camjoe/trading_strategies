from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from common.git import get_repo_root


@dataclass(frozen=True)
class ScopeRule:
    prefix: str
    mode: str
    reason: str
    high_risk: bool = False


@dataclass
class ScopeReport:
    changed_files: list[str]
    modes: set[str] = field(default_factory=set)
    high_risk: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


SCOPE_RULES = (
    ScopeRule("src/trading/interfaces/runtime/jobs/", "aggressive", "runtime job or scheduler change", True),
    ScopeRule("src/trading/interfaces/runtime/scheduling/", "aggressive", "runtime job or scheduler change", True),
    ScopeRule("src/infrastructure/brokers/", "aggressive", "broker adapter change", True),
    ScopeRule("src/infrastructure/database/", "aggressive", "database schema or migration change", True),
    ScopeRule("src/trading/services/execution/", "aggressive", "order submission, fill, or reconciliation change", True),
    ScopeRule("src/trading/services/auto_trading/", "aggressive", "auto-trading decision change", True),
    ScopeRule("src/trading/domain/auto_trading/", "aggressive", "sizing or order policy change", True),
    ScopeRule("src/trading/domain/risk_gate.py", "aggressive", "risk gate change", True),
    ScopeRule("src/trading/domain/broker_connection.py", "aggressive", "broker port change", True),
    ScopeRule("src/trading/repositories/orders.py", "aggressive", "order or fill persistence change", True),
    ScopeRule("src/trading/repositories/books.py", "aggressive", "book persistence change", True),
    ScopeRule("src/trading/repositories/ledger.py", "aggressive", "ledger persistence change", True),
    ScopeRule("src/trading/repositories/positions.py", "aggressive", "position persistence change", True),
    ScopeRule("src/trading/persistence/", "aggressive", "money encoding or transaction change", True),
    ScopeRule("apps/paper_trading_web/backend/routes/admin.py", "aggressive", "admin route change", True),
    ScopeRule("apps/paper_trading_web/backend/routes/", "contract", "backend API route change"),
    ScopeRule("apps/paper_trading_web/backend/schemas/", "contract", "backend API schema change"),
    ScopeRule("apps/paper_trading_web/frontend/src/", "contract", "frontend API consumer change"),
    ScopeRule("src/trading/", "architecture", "trading-layer change"),
)

NOTE_RULES = (
    ScopeRule("docs/", "standard", "documentation change"),
    ScopeRule(".ai/skills/", "standard", "skill workflow change"),
    ScopeRule("plan/", "standard", "plan document change"),
)

# A diff with at least this many changed lines outside documentation gets the Simplifier. Both pilot
# PRs (about 250 and 800 lines) produced cleanups; tune against the scorecard.
LARGE_DIFF_LINES = 200

DOC_PREFIXES = ("docs/", ".ai/", "plan/")
MODULE_SUFFIXES = (".py", ".ts", ".tsx")


def classify_paths(paths: list[str]) -> ScopeReport:
    report = ScopeReport(changed_files=sorted(paths))
    matched_files: set[str] = set()

    for path in report.changed_files:
        normalized = path.replace("\\", "/")
        for rule in SCOPE_RULES:
            if normalized == rule.prefix.rstrip("/") or normalized.startswith(rule.prefix):
                matched_files.add(path)
                report.modes.add(rule.mode)
                note = f"{normalized}: {rule.reason}"
                if rule.high_risk:
                    report.high_risk.append(note)
                else:
                    report.notes.append(note)
        for rule in NOTE_RULES:
            if normalized == rule.prefix.rstrip("/") or normalized.startswith(rule.prefix):
                matched_files.add(path)
                report.notes.append(f"{normalized}: {rule.reason}")

    if not report.modes and any(path not in matched_files for path in report.changed_files):
        report.modes.add("standard")
    if not report.changed_files:
        report.notes.append("No changed files detected.")
    return report


def _is_documentation(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized.endswith(".md") or normalized.startswith(DOC_PREFIXES)


def suggest_reviewers(
    report: ScopeReport,
    changed_lines: int = 0,
    added_modules: list[str] | None = None,
) -> list[tuple[str, str]]:
    """Pairs of (reviewer, reason) for the diff; empty for a documentation-only or empty diff."""
    if not report.changed_files or all(_is_documentation(path) for path in report.changed_files):
        return []

    reviewers = [
        ("Architecture and conventions", "code change"),
        ("Break it", "code change"),
        ("Test skeptic", "code change"),
    ]
    if "aggressive" in report.modes:
        reviewers.append(("Break it, second sample on Opus", "aggressive-mode paths"))
        reviewers.append(("Operator", "aggressive-mode paths"))
    if changed_lines >= LARGE_DIFF_LINES:
        reviewers.append(("Simplifier", f"{changed_lines} changed lines outside documentation"))
    elif added_modules:
        reviewers.append(("Simplifier", f"new module: {', '.join(sorted(added_modules))}"))
    return reviewers


def _git_output(repo_root: Path, command: list[str]) -> str:
    return subprocess.run(command, cwd=repo_root, check=True, capture_output=True, text=True).stdout


def _diff_range(base_ref: str | None) -> list[str]:
    return [f"{base_ref}...HEAD"] if base_ref else ["HEAD"]


def changed_files(repo_root: Path, base_ref: str | None = None) -> list[str]:
    output = _git_output(repo_root, ["git", "diff", "--name-only", *_diff_range(base_ref)])
    return [line.strip() for line in output.splitlines() if line.strip()]


def diff_stats(repo_root: Path, base_ref: str | None = None) -> tuple[int, list[str]]:
    """Changed lines outside documentation, and the source modules the diff adds."""
    numstat = _git_output(repo_root, ["git", "diff", "--numstat", *_diff_range(base_ref)])
    changed_lines = 0
    for line in numstat.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        if added.isdigit() and deleted.isdigit() and not _is_documentation(path):
            changed_lines += int(added) + int(deleted)

    added_output = _git_output(repo_root, ["git", "diff", "--diff-filter=A", "--name-only", *_diff_range(base_ref)])
    added_modules = [
        path
        for path in (line.strip().replace("\\", "/") for line in added_output.splitlines())
        if path.endswith(MODULE_SUFFIXES) and not path.startswith("tests/") and not path.endswith("__init__.py")
    ]
    return changed_lines, added_modules


def run_review_scope_check(repo_root: Path, *, base_ref: str | None = None, quiet: bool = False) -> int:
    try:
        report = classify_paths(changed_files(repo_root, base_ref=base_ref))
        changed_lines, added_modules = diff_stats(repo_root, base_ref=base_ref)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: failed to inspect git diff: {' '.join(exc.cmd)}")
        return exc.returncode

    if quiet and not report.changed_files:
        print("PASS: review scope - no changed files detected.")
        return 0

    print("Review Scope Check")
    print(f"Repo root: {repo_root}")
    print(f"Diff: {base_ref + '...HEAD' if base_ref else 'HEAD'}")
    print(f"Changed files: {len(report.changed_files)}")
    print(
        "Suggested review modes: " + ", ".join(sorted(report.modes))
        if report.modes
        else "Suggested review modes: none"
    )

    if report.high_risk:
        print("\nHigh-risk triggers:")
        for note in sorted(report.high_risk):
            print(f"- {note}")

    if report.notes:
        print("\nScope notes:")
        for note in sorted(report.notes):
            print(f"- {note}")

    reviewers = suggest_reviewers(report, changed_lines=changed_lines, added_modules=added_modules)
    if reviewers:
        print("\nSuggested reviewers:")
        for name, reason in reviewers:
            print(f"- {name}: {reason}")
    else:
        print("\nSuggested reviewers: none (documentation-only or empty diff)")

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify changed files into suggested code-review modes, high-risk triggers, and reviewers.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    parser.add_argument("--base", metavar="REF", default=None, help="Classify changes vs a git ref.")
    parser.add_argument("--quiet", action="store_true", help="Collapse empty output to one PASS line.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_review_scope_check(repo_root=repo_root, base_ref=args.base, quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
