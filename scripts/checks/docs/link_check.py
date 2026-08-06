from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from common.git import get_repo_root
from common.paths import relative_posix

# A markdown link or image: [text](target) / ![alt](target). Captures the target.
#   "[Docs Map](maps/docs-map.md)"  ->  captures "maps/docs-map.md"
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

# Any inline code span. Backtick path references (e.g. `docs/reference/agent-skills.md`) are
# checked when they look like a repo-root path (see TOP_DIRS below).
CODE_SPAN_RE = re.compile(r"`([^`]+)`")

# Link targets with these prefixes are external / non-filesystem and are not checked.
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "tel:", "ftp://", "//")

# A backtick span starting with one of these (e.g. `docs/...`, `.ai/...`) is a repo-root path
# reference and is checked for existence. Dotted module paths (no slash) never match.
TOP_DIRS = (
    "src/",
    "scripts/",
    "apps/",
    "tests/",
    "docs/",
    ".ai/",
    ".github/",
)

IGNORED_DIR_PARTS = {
    ".git",
    ".venv",
    "venv",
    "local",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "db_backups",
    "docs-migration",  # migration record: intentionally references moved/removed paths
}

# Files excluded from scanning. (None currently — the former exclusion, the verbatim upstream
# copy at docs/reference/agent-skills.md, was deleted.)
EXCLUDED_DOCS: tuple[str, ...] = ()

# Directory prefixes excluded from scanning. (None currently — the restructure
# planning docs that needed this were retired once the migration completed.)
EXCLUDED_DIR_PREFIXES: tuple[str, ...] = ()


@dataclass
class BrokenRef:
    line: int
    kind: str  # "link" (markdown link) or "path" (backtick repo-root path)
    target: str


@dataclass
class FileReport:
    path: Path
    broken: list[BrokenRef] = field(default_factory=list)


def discover_docs(repo_root: Path) -> list[Path]:
    docs: list[Path] = []
    for candidate in repo_root.rglob("*.md"):
        if any(part in IGNORED_DIR_PARTS for part in candidate.parts):
            continue
        rel = relative_posix(candidate, repo_root)
        if rel in EXCLUDED_DOCS:
            continue
        if any(rel.startswith(prefix) for prefix in EXCLUDED_DIR_PREFIXES):
            continue
        docs.append(candidate)
    return sorted(docs)


def _strip_target(target: str) -> str:
    """Drop a trailing #anchor and surrounding whitespace from a link target."""
    return target.split("#", 1)[0].strip()


def _is_external(target: str) -> bool:
    return target.startswith("#") or target.startswith(EXTERNAL_PREFIXES)


def _is_placeholder(text: str) -> bool:
    """A template path with a `<placeholder>` segment (e.g. `routes/<area>.py`) — not a real path."""
    return "<" in text or ">" in text


def _check_markdown_link(target: str, doc_dir: Path) -> bool:
    """True if the (relative) link target resolves to an existing file or directory."""
    stripped = _strip_target(target)
    if not stripped:
        return True  # pure anchor within the page
    return (doc_dir / stripped).exists()


def _path_token(span: str) -> str | None:
    """Return the first whitespace-delimited token of a backtick span if it looks like a path
    reference, else None.

    Only the first word is used, so trailing section pointers like "`docs/...md § Naming`" check
    just the file. Globs, brace-expansions, function-call notation (`config.get_db_path()`), and
    `<placeholder>` templates are not paths.
    """
    words = span.split()
    if not words:
        return None
    token = words[0]
    if any(ch in token for ch in "*(){}") or _is_placeholder(token):
        return None
    return token


def _check_backtick_path(span: str, repo_root: Path) -> bool | None:
    """Check a backtick span that looks like a current repo-root path. Returns None if it is not one."""
    token = _path_token(span)
    if token is None or not token.startswith(TOP_DIRS):
        return None
    base = token.split("#", 1)[0].split("::", 1)[0].rstrip("/")  # drop #anchor and ::symbol suffixes
    return (repo_root / base).exists()


def check_file(path: Path, repo_root: Path) -> FileReport:
    report = FileReport(path=path)
    doc_dir = path.parent
    in_fence = False
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue  # links/paths inside fenced code blocks are examples, not real references
        for target in MD_LINK_RE.findall(line):
            if _is_external(target) or _is_placeholder(target):
                continue
            if not _check_markdown_link(target, doc_dir):
                report.broken.append(BrokenRef(line=line_no, kind="link", target=target))
        for span in CODE_SPAN_RE.findall(line):
            resolved = _check_backtick_path(span, repo_root)
            if resolved is False:
                report.broken.append(BrokenRef(line=line_no, kind="path", target=span.strip()))
    return report


def run_link_check(repo_root: Path, *, enforce: bool = False, quiet: bool = False) -> int:
    if not repo_root.exists():
        print(f"ERROR: repo root does not exist: {repo_root}")
        return 2

    reports = [report for path in discover_docs(repo_root) if (report := check_file(path, repo_root)).broken]
    total = sum(len(report.broken) for report in reports)

    # Quiet mode: collapse a clean run to one line; broken refs fall through to the full report.
    if quiet and not total:
        print("PASS: doc links - all references resolve.")
        return 0

    print("Doc Link Check")
    print(f"Repo root: {repo_root}")
    print("Mode: " + ("enforced" if enforce else "advisory"))
    print(f"Broken references: {total}")

    if total:
        print("\nFindings:")
        for report in reports:
            rel = relative_posix(report.path, repo_root)
            for ref in report.broken:
                print(f"- {rel}:{ref.line} [{ref.kind}] {ref.target}")

    if enforce and total:
        print("\nFAIL: doc link check failed in enforce mode.")
        return 1
    if total:
        print("\nWARN: doc link check found broken references.")
    else:
        print("\nPASS: all doc links and path references resolve.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report markdown links and backtick repo-root paths in docs that do not resolve.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to detected workspace root.",
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Exit non-zero when broken references are found (default: advisory, always exit 0).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_link_check(repo_root=repo_root, enforce=args.enforce)


if __name__ == "__main__":
    raise SystemExit(main())
