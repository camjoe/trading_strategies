from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from common.paths.repo_paths import get_repo_root


# A backtick code span whose entire content is a module path, e.g. `accounts/queries.py`.
CODE_SPAN_RE = re.compile(r"`([^`]+)`")
PY_PATH_RE = re.compile(r"^[\w./-]+\.py$")

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


def _collect_all_py(repo_root: Path) -> set[str]:
    modules: set[str] = set()
    for path in repo_root.rglob("*.py"):
        if any(part in IGNORED_DIR_PARTS for part in path.parts):
            continue
        modules.add(_rel_posix(path, repo_root))
    return modules


def _extract_doc_py_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for span in CODE_SPAN_RE.findall(text):
        candidate = span.strip().replace("\\", "/")
        if PY_PATH_RE.match(candidate):
            tokens.add(candidate)
    return tokens


def _suffix_match(full_path: str, token: str) -> bool:
    """The map uses paths relative to a section, so match on path suffix."""
    return full_path == token or full_path.endswith("/" + token)


def check_map(repo_root: Path, map_rel: str, source_rel: str, skip: tuple[str, ...]) -> MapCheckReport:
    text = (repo_root / map_rel).read_text(encoding="utf-8", errors="replace")
    tokens = _extract_doc_py_tokens(text)
    source_modules = _collect_modules(repo_root / source_rel, repo_root, skip)
    all_modules = _collect_all_py(repo_root)

    report = MapCheckReport(map_path=repo_root / map_rel, source_root=source_rel)
    report.undocumented = sorted(
        module for module in source_modules if not any(_suffix_match(module, token) for token in tokens)
    )
    report.stale = sorted(token for token in tokens if not any(_suffix_match(module, token) for module in all_modules))
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
