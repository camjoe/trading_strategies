from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from common.paths.repo_paths import get_repo_root

from scripts.checks.link_check import discover_docs

# A `python -m <module>` invocation. Captures the dotted module path.
# Breakdown: (?<![\w-])-m\s+ = a standalone `-m` flag (not part of `--mod`/`xx-m`) + whitespace,
# then a dotted identifier. Numeric `-m 5` (e.g. `grep -m 5`) does not match (must start letter/_).
#   "python -m trading.interfaces.cli.main init"  ->  captures "trading.interfaces.cli.main"
MODULE_INVOCATION_RE = re.compile(r"(?<![\w-])-m\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)")


@dataclass
class BrokenRef:
    line: int
    module: str


@dataclass
class FileReport:
    path: Path
    broken: list[BrokenRef] = field(default_factory=list)


def _rel_posix(path: Path, repo_root: Path) -> str:
    return str(path.relative_to(repo_root)).replace("\\", "/")


def _search_roots(repo_root: Path) -> list[Path]:
    """Directories whose subtrees back first-party top-level package names.

    Mirrors the editable install: `src/` exposes trading/infrastructure/common,
    `apps/` exposes the web packages, and repo-root exposes `scripts`/`tests`.
    """
    return [root for root in (repo_root / "src", repo_root, repo_root / "apps") if root.is_dir()]


def _is_first_party(module: str, search_roots: list[Path]) -> bool:
    """True when the module's top-level segment is a directory under a search root.

    Stdlib/third-party targets (`json.tool`, `pip`, `pytest`) have no such directory and
    are skipped — we only validate modules this repo actually owns.
    """
    top = module.split(".", 1)[0]
    return any((root / top).is_dir() for root in search_roots)


def _resolves(module: str, search_roots: list[Path]) -> bool:
    """True when the dotted module maps to a file on disk: a `<...>.py` module, or a
    package directory exposing `__init__.py` / `__main__.py`."""
    parts = module.split(".")
    for root in search_roots:
        base = root.joinpath(*parts)
        if base.with_suffix(".py").is_file():
            return True
        if (base / "__init__.py").is_file() or (base / "__main__.py").is_file():
            return True
    return False


def check_file(path: Path, search_roots: list[Path]) -> FileReport:
    """Scan one markdown file for `-m <module>` invocations that name a first-party
    module which does not resolve. Unlike the link check, fenced code blocks are
    scanned — that is where runnable `-m` commands live."""
    report = FileReport(path=path)
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        for module in MODULE_INVOCATION_RE.findall(line):
            if not _is_first_party(module, search_roots):
                continue
            if not _resolves(module, search_roots):
                report.broken.append(BrokenRef(line=line_no, module=module))
    return report


def run_module_ref_check(repo_root: Path, *, enforce: bool = False, quiet: bool = False) -> int:
    if not repo_root.exists():
        print(f"ERROR: repo root does not exist: {repo_root}")
        return 2

    search_roots = _search_roots(repo_root)
    reports = [report for path in discover_docs(repo_root) if (report := check_file(path, search_roots)).broken]
    total = sum(len(report.broken) for report in reports)

    if quiet and not total:
        print("PASS: module refs - all `-m` invocations resolve.")
        return 0

    print("Doc Module Reference Check")
    print(f"Repo root: {repo_root}")
    print("Mode: " + ("enforced" if enforce else "advisory"))
    print(f"Stale `-m` module references: {total}")

    if total:
        print("\nFindings:")
        for report in reports:
            rel = _rel_posix(report.path, repo_root)
            for ref in report.broken:
                print(f"- {rel}:{ref.line} [module] {ref.module}")

    if enforce and total:
        print("\nFAIL: module reference check failed in enforce mode.")
        return 1
    if total:
        print("\nWARN: module reference check found stale `-m` invocations.")
    else:
        print("\nPASS: all `-m` module invocations resolve.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report `python -m <module>` invocations in docs whose first-party module does not resolve.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to detected workspace root.",
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Exit non-zero when stale references are found (default: advisory, always exit 0).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_module_ref_check(repo_root=repo_root, enforce=args.enforce)


if __name__ == "__main__":
    raise SystemExit(main())
