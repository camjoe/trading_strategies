from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from common.paths.formatting import relative_posix
from common.paths.repo_paths import get_repo_root


# The doc-header standard: docs/conventions/docs-authoring.md. Every file under docs/ carries a
# metadata block immediately after the H1 title. TEMPLATE.*.md files hold placeholder values and
# are exempt.

REQUIRED_FIELDS = ("Type", "Status", "Created", "Last Reviewed", "Purpose")
OPTIONAL_FIELDS = ("Related",)

TYPE_VOCAB = {
    "index",
    "map",
    "architecture",
    "runbook",
    "notes",
    "adr",
    "convention",
    "template",
    "policy",
    # Planning-doc family (overview/plan/decisions/specs/work orders).
    "overview",
    "plan",
    "spec",
    "implementation",
}

# The status is the leading token; a parenthetical or dash suffix adds context and is allowed
# (e.g. "Ready (multi-commit)", "Accepted — sequenced as P3").
STATUS_VOCAB = {
    "Active",
    "Draft",
    "Ready",
    "Complete",
    "Proposed",
    "Accepted",
    "Superseded",
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FIELD_RE = re.compile(r"^([A-Z][A-Za-z ]+):\s*(.*)$")
STATUS_TOKEN_RE = re.compile(r"^([A-Za-z]+)")


@dataclass
class HeaderReport:
    path: Path
    problems: list[str] = field(default_factory=list)


def discover_docs(repo_root: Path) -> list[Path]:
    docs_dir = repo_root / "docs"
    if not docs_dir.is_dir():
        return []
    return sorted(path for path in docs_dir.rglob("*.md") if not path.name.startswith("TEMPLATE."))


def parse_header(text: str) -> dict[str, str] | None:
    """Return the header fields following the H1 title, or None if no H1 is found.

    The header block runs from the first line after the H1 to the first blank line after any
    field has been seen. Wrapped field values (continuation lines) are tolerated and skipped.
    """
    lines = text.splitlines()
    h1_index = next((i for i, line in enumerate(lines) if line.startswith("# ")), None)
    if h1_index is None:
        return None

    fields: dict[str, str] = {}
    for line in lines[h1_index + 1 :]:
        if not line.strip():
            if fields:
                break  # blank line ends the header block
            continue  # blank line(s) between the H1 and the block
        match = FIELD_RE.match(line)
        if match:
            fields[match.group(1)] = match.group(2).strip()
        elif not fields:
            break  # body content with no header block at all
        # else: a wrapped continuation of the previous field's value — skip
    return fields


def check_file(path: Path) -> HeaderReport:
    report = HeaderReport(path=path)
    fields = parse_header(path.read_text(encoding="utf-8", errors="replace"))
    if fields is None:
        report.problems.append("no H1 title found")
        return report

    for name in REQUIRED_FIELDS:
        if name not in fields:
            report.problems.append(f"missing field: {name}")
        elif not fields[name]:
            report.problems.append(f"empty field: {name}")

    doc_type = fields.get("Type", "")
    if doc_type and doc_type not in TYPE_VOCAB:
        report.problems.append(f"unknown Type: {doc_type!r} (vocabulary: docs-authoring.md)")

    status = fields.get("Status", "")
    if status:
        token_match = STATUS_TOKEN_RE.match(status)
        token = token_match.group(1) if token_match else status
        if token not in STATUS_VOCAB:
            report.problems.append(f"unknown Status: {status!r} (vocabulary: docs-authoring.md)")

    for name in ("Created", "Last Reviewed"):
        value = fields.get(name, "")
        if value and not DATE_RE.match(value):
            report.problems.append(f"{name} is not an ISO date (YYYY-MM-DD): {value!r}")

    return report


def run_doc_header_check(repo_root: Path, *, enforce: bool = False, quiet: bool = False) -> int:
    if not repo_root.exists():
        print(f"ERROR: repo root does not exist: {repo_root}")
        return 2

    reports = [report for path in discover_docs(repo_root) if (report := check_file(path)).problems]
    total = sum(len(report.problems) for report in reports)

    if quiet and not total:
        print("PASS: doc headers - all docs carry a valid header block.")
        return 0

    print("Doc Header Check")
    print(f"Repo root: {repo_root}")
    print("Mode: " + ("enforced" if enforce else "advisory"))
    print(f"Header problems: {total}")

    if total:
        print("\nFindings:")
        for report in reports:
            rel = relative_posix(report.path, repo_root)
            for problem in report.problems:
                print(f"- {rel}: {problem}")

    if enforce and total:
        print("\nFAIL: doc header check failed in enforce mode.")
        return 1
    if total:
        print("\nWARN: doc header check found problems.")
    else:
        print("\nPASS: all docs carry a valid header block.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify every docs/ file carries the required header fields with valid vocabulary.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to detected workspace root.",
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Exit non-zero when problems are found (default: advisory, always exit 0).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_doc_header_check(repo_root=repo_root, enforce=args.enforce)


if __name__ == "__main__":
    raise SystemExit(main())
