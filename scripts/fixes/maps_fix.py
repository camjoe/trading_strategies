from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

from common.paths.formatting import relative_posix
from common.paths.repo_paths import get_repo_root

from scripts.checks.docs.maps_check import MAP_SPECS, iter_table_row_paths


# Fix counterpart of scripts.checks.docs.maps_check. Only the fully mechanical half of map
# drift is fixable: a table row whose every `.py` token points at a deleted file carries no
# recoverable information, so it is removed. Undocumented modules need human-written
# responsibility text, and rows mixing live and stale tokens need human judgment — both are
# reported and left in place.


@dataclass
class MapFixReport:
    map_path: Path
    removed: list[str] = field(default_factory=list)  # deleted rows (every token stale)
    mixed: list[str] = field(default_factory=list)  # kept rows mixing live and stale tokens


def _is_stale(path: str, repo_root: Path) -> bool:
    # Mirrors the staleness rule in maps_check.check_map: only slashed paths are resolvable
    # file-claims, so bare names are never treated as stale.
    return "/" in path and not (repo_root / path).is_file()


def fix_map(repo_root: Path, map_rel: str, source_rel: str) -> MapFixReport:
    map_path = repo_root / map_rel
    text = map_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    report = MapFixReport(map_path=map_path)
    drop: set[int] = set()
    for line_no, paths in iter_table_row_paths(text, source_rel):
        stale = [path for path in paths if _is_stale(path, repo_root)]
        if not stale:
            continue
        if len(stale) == len(paths):
            drop.add(line_no)
            report.removed.append(lines[line_no].strip())
        else:
            report.mixed.append(lines[line_no].strip())

    if drop:
        new_text = "\n".join(line for index, line in enumerate(lines) if index not in drop)
        if text.endswith("\n"):
            new_text += "\n"
        map_path.write_text(new_text, encoding="utf-8")
    return report


def run_maps_fix(repo_root: Path) -> int:
    if not repo_root.exists():
        print(f"ERROR: repo root does not exist: {repo_root}")
        return 2

    reports = []
    for map_rel, source_rel, _skip in MAP_SPECS:
        if not (repo_root / map_rel).is_file():
            print(f"NOTE: skipping missing map {map_rel}")
            continue
        reports.append(fix_map(repo_root, map_rel, source_rel))

    total_removed = sum(len(report.removed) for report in reports)
    total_mixed = sum(len(report.mixed) for report in reports)
    print(f"Stale map rows removed: {total_removed}")
    for report in reports:
        rel = relative_posix(report.map_path, repo_root)
        for row in report.removed:
            print(f"- {rel}: removed {row}")
        for row in report.mixed:
            print(f"- {rel}: NEEDS MANUAL EDIT (mixes live and stale paths): {row}")
    if total_mixed:
        print("\nRows mixing live and stale paths were left in place; fix those by hand.")
    if not (total_removed or total_mixed):
        print("No stale map rows found.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove structural-map table rows whose files no longer exist on disk.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to detected workspace root.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_maps_fix(repo_root=repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
