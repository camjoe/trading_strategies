from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from common.paths.repo_paths import get_repo_root


# --- Markdown parsing patterns. The map is read line by line; these pull out its structure. ---

# Any inline code span (text between a pair of backticks). Captures the inner text.
#   `accounts/queries.py`  ->  accounts/queries.py
CODE_SPAN_RE = re.compile(r"`([^`]+)`")

# True when the whole string is a module path ending in ".py" (only word chars, dots,
# slashes, hyphens; no spaces). Distinguishes a real path token from prose in backticks.
#   matches: accounts/queries.py        rejects: python -m scripts.run_checks
PY_PATH_RE = re.compile(r"^[\w./-]+\.py$")

# A markdown heading line (1-6 leading '#'). Captures the heading text after the hashes.
#   "### `trading/services/`"  ->  captures "`trading/services/`"
HEADER_RE = re.compile(r"^#{1,6}\s+(.*)$")

# The first backtick-wrapped path inside a heading; an optional trailing slash is dropped.
#   "### `trading/services/`"  ->  captures "trading/services"
HEADER_PATH_RE = re.compile(r"`([\w./-]+?)/?`")

# A bold label followed by its directory in parentheses; captures the directory.
# Breakdown: \*\*[^*]+\*\* = the **bold** label, then \s*\( ... \) = optional space + (`path/`).
#   "**Runtime jobs** (`trading/interfaces/runtime/jobs/`)"  ->  captures "trading/interfaces/runtime/jobs"
SUBSECTION_RE = re.compile(r"\*\*[^*]+\*\*\s*\(`([\w./-]+?)/?`\)")

# A token starting with one of these top-level dirs is already a full repo path (not section-relative).
KNOWN_TOP_DIRS = (
    "trading",
    "brokers",
    "features",
    "scripts",
    "paper_trading_ui",
    "tests",
    "common",
    "docs",
    ".github",
)

IGNORED_DIR_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "db_backups",
}

# (map file, source tree it documents, subtrees the map covers at DIRECTORY level only).
# Directory-summarized subtrees are skipped so their individual files are not flagged
# as "undocumented". Extend this list to cover ui-map.md / scripts-map.md later.
MAP_SPECS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "docs/maps/trading-package-map.md",
        "trading",
        (
            "trading/backtesting/domain",
            "trading/backtesting/repositories",
            "trading/backtesting/services",
            "trading/config",
        ),
    ),
)


@dataclass
class MapCheckReport:
    map_path: Path
    source_root: str
    undocumented: list[str] = field(default_factory=list)  # on disk, not named in the map
    stale: list[str] = field(default_factory=list)  # named in the map, no matching file


def _rel_posix(path: Path, repo_root: Path) -> str:
    return str(path.relative_to(repo_root)).replace("\\", "/")


def _collect_modules(root: Path, repo_root: Path, skip: tuple[str, ...]) -> set[str]:
    modules: set[str] = set()
    for path in root.rglob("*.py"):
        if any(part in IGNORED_DIR_PARTS for part in path.parts):
            continue
        if path.name == "__init__.py":
            continue
        rel = _rel_posix(path, repo_root)
        if any(rel == prefix or rel.startswith(prefix + "/") for prefix in skip):
            continue
        modules.add(rel)
    return modules


def _section_dir_from_heading(heading: str) -> str | None:
    match = HEADER_PATH_RE.search(heading)
    if not match:
        return None
    path = match.group(1).rstrip("/")
    return path if path.split("/", 1)[0] in KNOWN_TOP_DIRS else None


def _resolve_token(token: str, current_dir: str | None) -> str:
    if token.split("/", 1)[0] in KNOWN_TOP_DIRS:
        return token
    if current_dir:
        return f"{current_dir}/{token}"
    return token


def _extract_documented_paths(text: str) -> set[str]:
    """Resolve each `.py` token to a full repo path using its section/subsection directory.

    The map lists files relative to the section they sit under (e.g. `accounting.py` beneath
    ``### `trading/domain/` `` means ``trading/domain/accounting.py``). Tracking that context
    gives exact matches and avoids basename collisions across directories.
    """
    documented: set[str] = set()
    current_dir: str | None = None
    for line in text.splitlines():
        heading = HEADER_RE.match(line)
        if heading:
            current_dir = _section_dir_from_heading(heading.group(1))
            continue
        subsection = SUBSECTION_RE.search(line)
        if subsection:
            current_dir = subsection.group(1).rstrip("/")
            continue
        # Only table rows are file-claims; prose mentions (e.g. "the runtime_loader.py exception")
        # are not, so they should not be resolved into (often non-existent) section paths.
        if not line.lstrip().startswith("|"):
            continue
        for span in CODE_SPAN_RE.findall(line):
            candidate = span.strip().replace("\\", "/")
            if PY_PATH_RE.match(candidate):
                documented.add(_resolve_token(candidate, current_dir))
    return documented


def check_map(repo_root: Path, map_rel: str, source_rel: str, skip: tuple[str, ...]) -> MapCheckReport:
    text = (repo_root / map_rel).read_text(encoding="utf-8", errors="replace")
    documented = _extract_documented_paths(text)
    source_modules = _collect_modules(repo_root / source_rel, repo_root, skip)

    report = MapCheckReport(map_path=repo_root / map_rel, source_root=source_rel)
    report.undocumented = sorted(module for module in source_modules if module not in documented)
    report.stale = sorted(path for path in documented if "/" in path and not (repo_root / path).is_file())
    return report


def run_maps_check(repo_root: Path, *, enforce: bool = False) -> int:
    if not repo_root.exists():
        print(f"ERROR: repo root does not exist: {repo_root}")
        return 2

    reports = [check_map(repo_root, map_rel, source_rel, skip) for map_rel, source_rel, skip in MAP_SPECS]
    total_undocumented = sum(len(report.undocumented) for report in reports)
    total_stale = sum(len(report.stale) for report in reports)

    print("Maps Drift Check")
    print(f"Repo root: {repo_root}")
    print("Mode: " + ("enforced" if enforce else "advisory"))
    print(f"Undocumented modules (on disk, not in map): {total_undocumented}")
    print(f"Stale path tokens (in map, no matching file): {total_stale}")

    if total_undocumented or total_stale:
        print("\nFindings:")
        for report in reports:
            rel = _rel_posix(report.map_path, repo_root)
            if report.undocumented:
                print(f"- {rel} - {len(report.undocumented)} undocumented under {report.source_root}/:")
                for module in report.undocumented:
                    print(f"  + {module}")
            if report.stale:
                print(f"- {rel} - {len(report.stale)} stale path token(s):")
                for token in report.stale:
                    print(f"  - {token}")

    if enforce and (total_undocumented or total_stale):
        print("\nFAIL: maps drift check failed in enforce mode.")
        return 1
    if total_undocumented or total_stale:
        print("\nWARN: maps drift check found advisory issues (a human/skill writes the responsibilities).")
    else:
        print("\nPASS: maps in sync with source.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report drift between structural maps and the modules on disk (read-only).",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to detected workspace root.",
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Exit non-zero when drift is found (default: advisory, always exit 0).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_maps_check(repo_root=repo_root, enforce=args.enforce)


if __name__ == "__main__":
    raise SystemExit(main())
