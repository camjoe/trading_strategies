"""Sector reference-data coverage check.

Every symbol in a trade universe must appear in
``src/infrastructure/config/symbol_sectors.json``. A symbol missing from that map
is charged to the shared ``UNCATEGORIZED_SECTOR`` bucket by the risk gate, so it
competes for one cap with every other unmapped name — correct as a failsafe,
wrong as a steady state. Coverage drifts silently otherwise: adding a ticker to a
universe is a one-line edit that nothing else objects to.

Run standalone::

    python -m scripts.checks.repo.sector_map_check

Or call ``run_sector_map_check(repo_root)`` from other check scripts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common.git import get_repo_root
from common.paths import relative_posix

CONFIG_DIR = Path("src/infrastructure/config")
SECTOR_MAP_PATH = CONFIG_DIR / "symbol_sectors.json"
UNIVERSE_GLOBS = ("trade_universes/*.txt",)


def _load_sector_map(path: Path) -> dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be a JSON object of symbol -> sector")
    return {str(k).upper().strip(): str(v).strip().lower() for k, v in raw.items()}


def _load_universe(path: Path) -> set[str]:
    return {
        line.strip().upper()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def run_sector_map_check(repo_root: Path, *, quiet: bool = True) -> int:
    sector_map_path = repo_root / SECTOR_MAP_PATH
    if not sector_map_path.exists():
        print(f"FAIL: missing sector reference data: {SECTOR_MAP_PATH}")
        return 1

    sector_map = _load_sector_map(sector_map_path)
    blank = sorted(sym for sym, sector in sector_map.items() if not sector)
    if blank:
        print(f"FAIL: {len(blank)} symbol(s) mapped to a blank sector: {', '.join(blank)}")
        return 1

    universe_paths = sorted(
        {path for glob in UNIVERSE_GLOBS for path in (repo_root / CONFIG_DIR).glob(glob)},
    )
    if not universe_paths:
        print(f"FAIL: no trade universe files found under {CONFIG_DIR}")
        return 1

    failures = 0
    for path in universe_paths:
        missing = sorted(_load_universe(path) - set(sector_map))
        rel = relative_posix(path, repo_root)
        if missing:
            failures += 1
            print(f"FAIL: {rel}: {len(missing)} symbol(s) missing from {SECTOR_MAP_PATH.name}")
            print(f"      {', '.join(missing)}")
        elif not quiet:
            print(f"ok:   {rel}")

    if failures:
        print(f"\nAdd the symbols above to {SECTOR_MAP_PATH.as_posix()} with their sector.")
        return 1

    if not quiet:
        print(f"\n{len(universe_paths)} universe file(s) fully covered by {len(sector_map)} sector mappings.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that every trade-universe symbol has a sector mapping.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to detected workspace root.",
    )
    parser.add_argument("--verbose", action="store_true", help="List covered universe files too.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    exit_code = run_sector_map_check(repo_root, quiet=not args.verbose)
    if exit_code == 0:
        print("\nSector map coverage check completed successfully.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
