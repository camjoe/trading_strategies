from __future__ import annotations

import argparse
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from common.paths.formatting import relative_posix
from common.paths.repo_paths import get_repo_root


# --- Markdown parsing patterns. The map is read line by line; these pull out its structure. ---

# Any inline code span (text between a pair of backticks). Captures the inner text.
#   `accounts/queries.py`  ->  accounts/queries.py
CODE_SPAN_RE = re.compile(r"`([^`]+)`")

# True when the whole string is a module path ending in ".py" (only word chars, dots,
# slashes, hyphens; no spaces). Distinguishes a real path token from prose in backticks.
#   matches: accounts/queries.py        rejects: python -m scripts.run_checks
PY_PATH_RE = re.compile(r"^[\w./-]+\.py$")

# A markdown heading line. Captures (leading hashes, heading text) so the level is known.
#   "### `trading/services/`"  ->  groups ("###", "`trading/services/`")
HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$")

# The first backtick-wrapped path inside a heading; an optional trailing slash is dropped.
#   "### `trading/services/`"  ->  captures "trading/services"
HEADER_PATH_RE = re.compile(r"`([\w./-]+?)/?`")

# A bold label followed by its directory in parentheses; captures the directory.
# Breakdown: \*\*[^*]+\*\* = the **bold** label, then \s*\( ... \) = optional space + (`path/`).
#   "**Runtime jobs** (`trading/interfaces/runtime/jobs/`)"  ->  captures "trading/interfaces/runtime/jobs"
SUBSECTION_RE = re.compile(r"\*\*[^*]+\*\*\s*\(`([\w./-]+?)/?`\)")

# A token starting with one of these top-level dirs is already a full repo path (not section-relative).
KNOWN_TOP_DIRS = (
    "src",
    "apps",
    "scripts",
    "tests",
    "docs",
    ".ai",
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
# Directory-summarized subtrees are skipped so their individual files are not flagged as
# "undocumented". The checker is Python-only: ui-map's source is the backend (the TypeScript
# frontend has no .py and is out of scope).
MAP_SPECS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "docs/maps/trading-package-map.md",
        "src/trading",
        (
            "src/trading/backtesting/domain",
            "src/trading/backtesting/repositories",
            "src/trading/backtesting/services",
            # models/ is directory-summarized by contract name (one contract per file),
            # not enumerated file-by-file; see the `### src/trading/models/` section.
            "src/trading/models",
        ),
    ),
    (
        "docs/maps/infrastructure-map.md",
        "src/infrastructure",
        (),
    ),
    (
        "docs/maps/common-map.md",
        "src/common",
        (),
    ),
    (
        "docs/maps/scripts-map.md",
        "scripts",
        (
            "scripts/documentation_ui/api",
            "scripts/documentation_ui/finance",
            "scripts/documentation_ui/software",
        ),
    ),
    (
        "docs/maps/ui-map.md",
        "apps/paper_trading_web/backend",
        (
            "apps/paper_trading_web/backend/services/accounts",
            "apps/paper_trading_web/backend/services/features",
            "apps/paper_trading_web/backend/services/operations",
        ),
    ),
)


@dataclass
class MapCheckReport:
    map_path: Path
    source_root: str
    undocumented: list[str] = field(default_factory=list)  # on disk, not named in the map
    stale: list[str] = field(default_factory=list)  # named in the map, no matching file


def _collect_modules(root: Path, repo_root: Path, skip: tuple[str, ...]) -> set[str]:
    modules: set[str] = set()
    for path in root.rglob("*.py"):
        if any(part in IGNORED_DIR_PARTS for part in path.parts):
            continue
        if path.name == "__init__.py":
            continue
        rel = relative_posix(path, repo_root)
        if any(rel == prefix or rel.startswith(prefix + "/") for prefix in skip):
            continue
        modules.add(rel)
    return modules


def _heading_path(heading_text: str) -> str | None:
    """First backtick path in a heading's text, trailing slash dropped; None if absent."""
    match = HEADER_PATH_RE.search(heading_text)
    return match.group(1).rstrip("/") if match else None


def _is_full_path(path: str) -> bool:
    """True when a path is repo-root-relative (starts with a known top-level directory)."""
    return path.split("/", 1)[0] in KNOWN_TOP_DIRS


def _resolve_token(token: str, current_dir: str) -> str:
    """Resolve a section-relative token to a full repo path; full-path tokens pass through."""
    return token if _is_full_path(token) else f"{current_dir}/{token}"


def iter_table_row_paths(text: str, source_rel: str) -> Iterator[tuple[int, list[str]]]:
    """Yield (line index, resolved repo paths) for each table row naming at least one `.py` file.

    Each `.py` token is resolved to a full repo path using its section context. Section
    directories may be full (``### `trading/services/` ``) or relative to a parent
    section (``### Routes (`routes/`)`` under ``## Backend (`apps/paper_trading_web/backend/`)``).
    Heading level disambiguates: a level-1/2 heading starts a top-level section (resolved against
    the source root); a deeper heading or bold label is a subsection (resolved against the current
    section base). Only table rows count as file-claims, so prose mentions are ignored.
    """
    section_base = source_rel  # dir set by the most recent top-level (#/##) section
    current_dir = source_rel  # dir the current table rows resolve against
    for line_no, line in enumerate(text.splitlines()):
        heading = HEADER_RE.match(line)
        if heading:
            path = _heading_path(heading.group(2))
            if len(heading.group(1)) <= 2:
                if path is None:
                    section_base = source_rel
                elif _is_full_path(path):
                    section_base = path
                else:
                    section_base = f"{source_rel}/{path}"
                current_dir = section_base
            elif path is None:
                current_dir = section_base
            elif _is_full_path(path):
                current_dir = path
            else:
                current_dir = f"{section_base}/{path}"
            continue
        subsection = SUBSECTION_RE.search(line)
        if subsection:
            path = subsection.group(1).rstrip("/")
            current_dir = path if _is_full_path(path) else f"{section_base}/{path}"
            continue
        # Only table rows are file-claims; prose mentions (e.g. "the runtime_loader.py exception")
        # are not, so they should not be resolved into (often non-existent) section paths.
        if not line.lstrip().startswith("|"):
            continue
        paths: list[str] = []
        for span in CODE_SPAN_RE.findall(line):
            candidate = span.strip().replace("\\", "/")
            if PY_PATH_RE.match(candidate):
                paths.append(_resolve_token(candidate, current_dir))
        if paths:
            yield line_no, paths


def _extract_documented_paths(text: str, source_rel: str) -> set[str]:
    """All resolved `.py` paths claimed by the map's table rows (see iter_table_row_paths)."""
    documented: set[str] = set()
    for _, paths in iter_table_row_paths(text, source_rel):
        documented.update(paths)
    return documented


def check_map(repo_root: Path, map_rel: str, source_rel: str, skip: tuple[str, ...]) -> MapCheckReport:
    text = (repo_root / map_rel).read_text(encoding="utf-8", errors="replace")
    documented = _extract_documented_paths(text, source_rel)
    source_modules = _collect_modules(repo_root / source_rel, repo_root, skip)

    report = MapCheckReport(map_path=repo_root / map_rel, source_root=source_rel)
    report.undocumented = sorted(module for module in source_modules if module not in documented)
    report.stale = sorted(path for path in documented if "/" in path and not (repo_root / path).is_file())
    return report


def run_maps_check(repo_root: Path, *, enforce: bool = False, quiet: bool = False) -> int:
    if not repo_root.exists():
        print(f"ERROR: repo root does not exist: {repo_root}")
        return 2

    reports = []
    for map_rel, source_rel, skip in MAP_SPECS:
        if not (repo_root / map_rel).is_file():
            print(f"NOTE: skipping missing map {map_rel}")
            continue
        reports.append(check_map(repo_root, map_rel, source_rel, skip))
    total_undocumented = sum(len(report.undocumented) for report in reports)
    total_stale = sum(len(report.stale) for report in reports)

    # Quiet mode: collapse a clean run to one line; drift falls through to the full report.
    if quiet and not (total_undocumented or total_stale):
        print(f"PASS: maps drift - {len(reports)} maps in sync with source.")
        return 0

    print("Maps Drift Check")
    print(f"Repo root: {repo_root}")
    print("Mode: " + ("enforced" if enforce else "advisory"))
    print(f"Undocumented modules (on disk, not in map): {total_undocumented}")
    print(f"Stale path tokens (in map, no matching file): {total_stale}")

    if total_undocumented or total_stale:
        print("\nFindings:")
        for report in reports:
            rel = relative_posix(report.map_path, repo_root)
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
