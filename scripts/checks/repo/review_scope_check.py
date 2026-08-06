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
    ScopeRule("apps/paper_trading_web/backend/routes/admin.py", "aggressive", "admin route change", True),
    ScopeRule("apps/paper_trading_web/backend/routes/", "contract", "backend API route change"),
    ScopeRule("apps/paper_trading_web/backend/schemas/", "contract", "backend API schema change"),
    ScopeRule("apps/paper_trading_web/frontend/src/", "contract", "frontend API consumer change"),
    ScopeRule("src/trading/", "architecture", "trading-layer change"),
)

NOTE_RULES = (
    ScopeRule("docs/", "standard", "documentation change"),
    ScopeRule(".ai/skills/", "standard", "skill workflow change"),
)


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


def changed_files(repo_root: Path, base_ref: str | None = None) -> list[str]:
    if base_ref:
        command = ["git", "diff", "--name-only", f"{base_ref}...HEAD"]
    else:
        command = ["git", "diff", "--name-only", "HEAD"]
    completed = subprocess.run(command, cwd=repo_root, check=True, capture_output=True, text=True)
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def run_review_scope_check(repo_root: Path, *, base_ref: str | None = None, quiet: bool = False) -> int:
    try:
        report = classify_paths(changed_files(repo_root, base_ref=base_ref))
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

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify changed files into suggested code-review modes and high-risk triggers.",
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
