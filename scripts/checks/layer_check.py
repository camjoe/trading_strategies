"""Layer boundary enforcement check.

Scans Python source files and fails if any module imports from a layer it is
not allowed to depend on, as defined in docs/architecture/architecture-conventions.md.

Each rule declares:
  - source_glob: the subtree being constrained
  - forbidden_prefixes: import prefixes that must not appear in that subtree
  - label: human-readable name shown in violation output

Run standalone::

    python -m scripts.checks.layer_check

Or call ``run_layer_check(repo_root)`` from other check scripts.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path

from common.paths.repo_paths import get_repo_root


# ---------------------------------------------------------------------------
# Rules — edit this table to add or change layer constraints.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayerRule:
    label: str
    source_glob: str
    forbidden_prefixes: tuple[str, ...]
    # Relative paths (posix) exempted from this rule. Use sparingly and
    # only when the import is at a deliberate architectural boundary.
    exceptions: tuple[str, ...] = ()


LAYER_RULES: list[LayerRule] = [
    LayerRule(
        label="apps/paper_trading_web → no direct repository imports",
        source_glob="apps/paper_trading_web/**/*.py",
        forbidden_prefixes=("trading.repositories.",),
    ),
    LayerRule(
        label="apps/paper_trading_web → no direct database imports",
        source_glob="apps/paper_trading_web/**/*.py",
        forbidden_prefixes=("infrastructure.database.",),
        # db.py is the interface-boundary connection factory: the single
        # point where ensure_db() is called to open connections for each
        # request. All other UI backend code receives conn via db_conn().
        exceptions=("apps/paper_trading_web/backend/services/db.py",),
    ),
    LayerRule(
        label="apps/paper_trading_web → no direct interface-layer imports",
        source_glob="apps/paper_trading_web/**/*.py",
        forbidden_prefixes=("trading.interfaces.",),
    ),
    LayerRule(
        label="trading/services → no direct database imports",
        source_glob="src/trading/services/**/*.py",
        forbidden_prefixes=("infrastructure.database.",),
        # runtime_loader.py is the deliberate exception: its sole purpose is to
        # open a DB connection for runtime job runners that don't have an injected
        # connection.  All other service modules must route through repositories.
        exceptions=("src/trading/services/accounts/runtime_loader.py",),
    ),
    LayerRule(
        label="trading/services → no interface-layer imports",
        source_glob="src/trading/services/**/*.py",
        forbidden_prefixes=("trading.interfaces.",),
    ),
    LayerRule(
        label="trading/backtesting/services → no direct database imports",
        source_glob="src/trading/backtesting/services/**/*.py",
        forbidden_prefixes=("infrastructure.database.",),
    ),
    LayerRule(
        label="trading/domain → no repository imports",
        source_glob="src/trading/domain/**/*.py",
        forbidden_prefixes=("trading.repositories.",),
    ),
    LayerRule(
        label="trading/domain → no database imports",
        source_glob="src/trading/domain/**/*.py",
        forbidden_prefixes=("infrastructure.database.",),
    ),
    LayerRule(
        label="trading/repositories → no interface imports",
        source_glob="src/trading/repositories/**/*.py",
        forbidden_prefixes=("trading.interfaces.",),
    ),
    LayerRule(
        label="trading → no direct market-data adapter imports (wire at composition roots)",
        source_glob="src/trading/**/*.py",
        forbidden_prefixes=("infrastructure.market_data.",),
        # The concrete adapter + factory are wired in at composition seams only:
        # the interface layer (CLI / runtime jobs) and the backtest entry seam.
        # All other trading code depends on the MarketDataProvider port + an
        # injected instance, never the concrete adapter.
        exceptions=(
            "src/trading/interfaces/cli/main.py",
            "src/trading/interfaces/runtime/jobs/run_auto_trades.py",
            "src/trading/backtesting/backtest.py",
        ),
    ),
    LayerRule(
        label="apps/paper_trading_web/routes → no direct feature-provider imports",
        source_glob="apps/paper_trading_web/backend/routes/**/*.py",
        forbidden_prefixes=("infrastructure.feature_providers.",),
    ),
    LayerRule(
        label="apps/paper_trading_web/routes → no direct trading.backtesting.domain imports",
        source_glob="apps/paper_trading_web/backend/routes/**/*.py",
        forbidden_prefixes=("trading.backtesting.domain.",),
    ),
]


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


@dataclass
class Violation:
    rule_label: str
    file: Path
    line: int
    import_text: str


def _extract_imports(source: str) -> list[tuple[int, str]]:
    """Return (lineno, dotted_module) for every import in source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    results: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                results.append((node.lineno, node.module))
    return results


_IGNORED_PARTS = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "dist",
        "build",
        "coverage",
    }
)


def _discover_files(repo_root: Path, glob: str) -> list[Path]:
    files: list[Path] = []
    for path in repo_root.glob(glob):
        if not path.is_file():
            continue
        if any(part in _IGNORED_PARTS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def check_rule(repo_root: Path, rule: LayerRule) -> list[Violation]:
    violations: list[Violation] = []
    for path in _discover_files(repo_root, rule.source_glob):
        rel_posix = path.relative_to(repo_root).as_posix()
        if rel_posix in rule.exceptions:
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, module in _extract_imports(source):
            for prefix in rule.forbidden_prefixes:
                if module == prefix.rstrip(".") or module.startswith(prefix):
                    violations.append(
                        Violation(
                            rule_label=rule.label,
                            file=path,
                            line=lineno,
                            import_text=module,
                        )
                    )
    return violations


def run_layer_check(repo_root: Path, *, rules: list[LayerRule] | None = None) -> int:
    """Run all layer rules and print a report. Returns 0 if clean, 1 if violations found."""
    active_rules = rules if rules is not None else LAYER_RULES
    all_violations: list[Violation] = []

    for rule in active_rules:
        all_violations.extend(check_rule(repo_root, rule))

    if not all_violations:
        print("Layer check passed. No boundary violations found.")
        return 0

    print(f"Layer check FAILED — {len(all_violations)} violation(s) found:\n")
    by_rule: dict[str, list[Violation]] = {}
    for v in all_violations:
        by_rule.setdefault(v.rule_label, []).append(v)

    for label, violations in by_rule.items():
        print(f"  Rule: {label}")
        for v in violations:
            rel = v.file.relative_to(repo_root)
            print(f"    {rel}:{v.line}  import {v.import_text}")
        print()

    return 1


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that layer boundaries defined in docs/architecture/architecture-conventions.md are respected.",
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
    exit_code = run_layer_check(repo_root)
    if exit_code == 0:
        print("\nLayer boundary check completed successfully.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
