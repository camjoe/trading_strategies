from __future__ import annotations

import ast
import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common.git import get_repo_root
from scripts.documentation_ui.commands.introspect import (
    KIND_JOB,
    KIND_TOOL,
    RISK_BROKER,
    RISK_READ_ONLY,
    RISK_WRITES_LOCAL,
    SCOPE_GLOBAL,
    capture_parser,
    describe_arguments,
    make_row,
    subcommand_helps,
    subparsers_action,
)
from trading.interfaces.runtime.scheduling.job_catalog import JOB_CATALOG

GROUP_DAILY_JOBS = "Daily Jobs"
GROUP_GOVERNANCE_JOBS = "Governance Jobs"
GROUP_MAINTENANCE_JOBS = "Maintenance Jobs"
GROUP_QUALITY = "Quality Checks"
GROUP_DATA = "Data and Database"
GROUP_LAUNCHERS = "Launchers and Demo"
GROUP_DOCS_SYNC = "Documentation Sync"
GROUP_BROKER_SMOKE = "Broker Smoke Tests"
GROUP_RESEARCH = "Research"
GROUP_SCHEDULING = "Scheduling"
GROUP_OPERATIONS = "Operations"

JOBS = "trading.interfaces.runtime.jobs"
RUNTIME = "trading.interfaces.runtime"

FAMILY_LAUNCH = "Launch the UI"
FAMILY_DIAGRAMS = "Database diagrams"
FAMILY_CHECKS = "Individual checks"
FAMILY_DOCS_SYNC = "Reference doc sync"
FAMILY_IBKR_SMOKE = "IBKR smoke tests"

# The UI shows each family as one row; its members open from that row. A tool with
# subcommands is a family named after the tool, so it needs an entry here too.
FAMILIES: dict[str, str] = {
    "run-checks": "Run a bundle of checks: docs, repo, python, quick (repo + python), or ci (everything).",
    FAMILY_CHECKS: "Each check as its own command. run-checks runs them in bundles.",
    FAMILY_LAUNCH: "Start the backend and frontend against the real, demo, or sandbox database.",
    "db-migrations": "Show, apply, or revert database schema revisions.",
    "db-admin": "List accounts, back up the database, or delete an account.",
    FAMILY_DIAGRAMS: "Build HTML database diagrams from the code-defined schema or a SQLite file.",
    FAMILY_DOCS_SYNC: "Sync or check generated reference docs and assets. fix-checks runs the sync and both fixers.",
    FAMILY_IBKR_SMOKE: "Read-only IBKR connection checks: Client Portal Web API or TWS / IB Gateway socket.",
}


@dataclass(frozen=True)
class EntrypointSpec:
    """Curated facts about one runnable module that its argparse parser cannot give."""

    module: str
    name: str
    kind: str
    group: str
    risk: str
    help: str = ""
    cadence: str | None = None
    sub_risks: dict[str, str] = field(default_factory=dict)
    capture: bool = True
    family: str | None = None


def _job(module: str, name: str, group: str, risk: str, cadence: str) -> EntrypointSpec:
    return EntrypointSpec(module=module, name=name, kind=KIND_JOB, group=group, risk=risk, cadence=cadence)


def _tool(module: str, name: str, group: str, risk: str, **extra: Any) -> EntrypointSpec:
    return EntrypointSpec(module=module, name=name, kind=KIND_TOOL, group=group, risk=risk, **extra)


JOB_SPECS: tuple[EntrypointSpec, ...] = (
    _job(f"{JOBS}.daily.paper_trading", "daily-paper-trading", GROUP_DAILY_JOBS, RISK_BROKER, "manual"),
    _job(
        f"{JOBS}.daily.challenger_shadow_eval", "challenger-shadow-eval", GROUP_DAILY_JOBS, RISK_WRITES_LOCAL, "manual"
    ),
    _job(f"{JOBS}.daily.trader_health", "trader-health", GROUP_DAILY_JOBS, RISK_WRITES_LOCAL, "manual"),
    _job(f"{JOBS}.daily.paper_trading.run_auto_trades", "run-auto-trades", GROUP_DAILY_JOBS, RISK_BROKER, "indirect"),
    _job(
        f"{JOBS}.daily.paper_trading.reconcile_orders", "reconcile-orders", GROUP_DAILY_JOBS, RISK_BROKER, "indirect"
    ),
    _job(
        f"{JOBS}.maintenance.weekly_db_backup", "weekly-db-backup", GROUP_MAINTENANCE_JOBS, RISK_WRITES_LOCAL, "manual"
    ),
    _job(f"{JOBS}.maintenance.burn_in_status", "burn-in-status", GROUP_MAINTENANCE_JOBS, RISK_WRITES_LOCAL, "manual"),
    _job(f"{JOBS}.maintenance.replay_daily_runs", "replay-daily-runs", GROUP_MAINTENANCE_JOBS, RISK_BROKER, "manual"),
    _job(
        f"{JOBS}.governance.weekly.w1_leaderboard",
        "w1-leaderboard",
        GROUP_GOVERNANCE_JOBS,
        RISK_WRITES_LOCAL,
        "weekly guard",
    ),
    _job(
        f"{JOBS}.governance.weekly.w2_promotion_review",
        "w2-promotion-review",
        GROUP_GOVERNANCE_JOBS,
        RISK_WRITES_LOCAL,
        "weekly guard",
    ),
    _job(
        f"{JOBS}.governance.weekly.w3_allocation_review",
        "w3-allocation-review",
        GROUP_GOVERNANCE_JOBS,
        RISK_WRITES_LOCAL,
        "weekly guard",
    ),
    _job(
        f"{JOBS}.governance.monthly.m1_risk_rebaseline",
        "m1-risk-rebaseline",
        GROUP_GOVERNANCE_JOBS,
        RISK_WRITES_LOCAL,
        "monthly guard",
    ),
    _job(
        f"{JOBS}.governance.monthly.m2_parameter_governance",
        "m2-parameter-governance",
        GROUP_GOVERNANCE_JOBS,
        RISK_WRITES_LOCAL,
        "monthly guard",
    ),
    _job(
        f"{JOBS}.governance.monthly.m3_performance_audit",
        "m3-performance-audit",
        GROUP_GOVERNANCE_JOBS,
        RISK_WRITES_LOCAL,
        "monthly guard",
    ),
)

TOOL_SPECS: tuple[EntrypointSpec, ...] = (
    _tool("scripts.run_checks", "run-checks", GROUP_QUALITY, RISK_READ_ONLY),
    _tool("scripts.fix_checks", "fix-checks", GROUP_QUALITY, RISK_WRITES_LOCAL),
    _tool(
        "scripts.launch_ui",
        "launch-ui",
        GROUP_LAUNCHERS,
        RISK_WRITES_LOCAL,
        help="Start the backend and frontend together.",
        family=FAMILY_LAUNCH,
    ),
    _tool(
        "scripts.launch_demo",
        "launch-demo",
        GROUP_LAUNCHERS,
        RISK_WRITES_LOCAL,
        help="Rebuild the synthetic offline demo database, then start the UI on separate ports.",
        family=FAMILY_LAUNCH,
    ),
    _tool("scripts.launch_sandbox", "launch-sandbox", GROUP_LAUNCHERS, RISK_WRITES_LOCAL, family=FAMILY_LAUNCH),
    _tool("scripts.screenshot_ui", "screenshot-ui", GROUP_LAUNCHERS, RISK_READ_ONLY),
    _tool("scripts.check_jobs", "check-jobs", GROUP_OPERATIONS, RISK_WRITES_LOCAL),
    _tool(
        "scripts.ibkr_web_api_smoke_test",
        "ibkr-web-api-smoke-test",
        GROUP_BROKER_SMOKE,
        RISK_BROKER,
        family=FAMILY_IBKR_SMOKE,
    ),
    _tool(
        "scripts.ibkr_socket_smoke_test",
        "ibkr-socket-smoke-test",
        GROUP_BROKER_SMOKE,
        RISK_BROKER,
        family=FAMILY_IBKR_SMOKE,
    ),
    _tool("scripts.benchmark_sweep", "benchmark-sweep", GROUP_RESEARCH, RISK_WRITES_LOCAL),
    _tool("scripts.data_ops.describe_db_schema", "describe-db-schema", GROUP_DATA, RISK_READ_ONLY),
    _tool("scripts.data_ops.check_cash_invariant", "check-cash-invariant", GROUP_DATA, RISK_READ_ONLY),
    _tool(
        "scripts.data_ops.build_database_diagram_viewer",
        "build-database-diagram-viewer",
        GROUP_DATA,
        RISK_WRITES_LOCAL,
        family=FAMILY_DIAGRAMS,
    ),
    _tool("scripts.data_ops.capture_scenario_fixture", "capture-scenario-fixture", GROUP_DATA, RISK_WRITES_LOCAL),
    _tool(
        "scripts.data_ops.manage_db_migrations",
        "db-migrations",
        GROUP_DATA,
        RISK_WRITES_LOCAL,
        sub_risks={"status": RISK_READ_ONLY, "history": RISK_READ_ONLY},
    ),
    _tool(
        f"{RUNTIME}.data_ops.admin",
        "db-admin",
        GROUP_DATA,
        RISK_WRITES_LOCAL,
        sub_risks={"list-accounts": RISK_READ_ONLY},
    ),
    _tool(f"{RUNTIME}.data_ops.seed_clean_schema", "seed-clean-schema", GROUP_DATA, RISK_WRITES_LOCAL),
    _tool(f"{RUNTIME}.scheduling.manage_job_schedules", "manage-job-schedules", GROUP_SCHEDULING, RISK_WRITES_LOCAL),
    _tool(
        "scripts.documentation_ui.sync",
        "sync-reference-docs",
        GROUP_DOCS_SYNC,
        RISK_WRITES_LOCAL,
        family=FAMILY_DOCS_SYNC,
    ),
    _tool(
        "scripts.documentation_ui.check",
        "check-reference-docs",
        GROUP_DOCS_SYNC,
        RISK_READ_ONLY,
        family=FAMILY_DOCS_SYNC,
    ),
    _tool(
        "scripts.fixes.db_schema_fix", "fix-db-schema-doc", GROUP_DOCS_SYNC, RISK_WRITES_LOCAL, family=FAMILY_DOCS_SYNC
    ),
    _tool("scripts.fixes.maps_fix", "fix-maps-doc", GROUP_DOCS_SYNC, RISK_WRITES_LOCAL, family=FAMILY_DOCS_SYNC),
    _tool("scripts.database_diagrams.sqlite", "sqlite-diagram", GROUP_DATA, RISK_WRITES_LOCAL, family=FAMILY_DIAGRAMS),
    _tool(
        "scripts.database_diagrams.render_html",
        "render-diagram-html",
        GROUP_DATA,
        RISK_WRITES_LOCAL,
        family=FAMILY_DIAGRAMS,
    ),
)

# Tool rows the web UI may run: read-only, and done in seconds. Entries that install packages,
# run the test suite, or run the type checker are not listed.
RUNNABLE_TOOLS = frozenset(
    {
        "describe-db-schema",
        "check-cash-invariant",
        "check-reference-docs",
        "db-admin list-accounts",
        "db-migrations status",
        "db-migrations history",
        "layer-check",
        "live-safety-check",
        "secret-hygiene-check",
        "path-safety-check",
        "migration-check",
        "sector-map-check",
        "skills-check",
        "doc-header-check",
        "doc-naming-check",
        "link-check",
        "maps-check",
        "module-ref-check",
        "readme-check",
        "db-schema-check",
    }
)

# Modules under these roots that define `main` are listed without a spec entry.
FAMILY_ROOT = "scripts/checks"
FAMILY_GROUP = GROUP_QUALITY
# Modules under FAMILY_ROOT that keep their own catalog row instead of joining FAMILY_CHECKS.
STANDALONE_CHECK_MODULES = frozenset({"scripts.checks.run_suite"})

# Modules that define `main` but are wrapped by a listed entry, so they stay off the page.
EXCLUDED_MODULE_PREFIXES: tuple[str, ...] = (
    "scripts.documentation_ui.api.",
    "scripts.documentation_ui.commands.",
    "scripts.documentation_ui.finance.",
    "scripts.documentation_ui.overview.",
    "scripts.documentation_ui.software.",
)

# Launchers that take no arguments build no parser to read.
PARSERLESS_MODULES = frozenset({"scripts.launch_ui", "scripts.launch_demo"})

SCAN_ROOTS: tuple[str, ...] = ("scripts", "src/trading/interfaces/runtime")


def _module_name(path: Path, repo_root: Path) -> str:
    relative = path.relative_to(repo_root).with_suffix("")
    parts = list(relative.parts)
    if parts[0] == "src":
        parts = parts[1:]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _defines_main(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return any(isinstance(node, ast.FunctionDef) and node.name == "main" for node in tree.body)


def discover_main_modules(repo_root: Path) -> dict[str, Path]:
    """Map module name -> file for every module under the scan roots that defines ``main``."""
    found: dict[str, Path] = {}
    for root in SCAN_ROOTS:
        for path in sorted((repo_root / root).rglob("*.py")):
            if "__pycache__" in path.parts or not _defines_main(path):
                continue
            found[_module_name(path, repo_root)] = path
    return found


def _family_modules(discovered: dict[str, Path], repo_root: Path) -> dict[str, Path]:
    family_dir = repo_root / FAMILY_ROOT
    return {module: path for module, path in discovered.items() if family_dir in path.parents}


def _calls_parse_args(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return any(
        isinstance(node, ast.Attribute) and node.attr in {"parse_args", "parse_known_args"} for node in ast.walk(tree)
    )


def _first_docstring_line(path: Path) -> str:
    docstring = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8-sig")))
    return " ".join(docstring.split("\n\n", 1)[0].split()) if docstring else ""


def _family_specs(discovered: dict[str, Path], repo_root: Path) -> list[EntrypointSpec]:
    specs: list[EntrypointSpec] = []
    for module, path in _family_modules(discovered, repo_root).items():
        name = module.removeprefix("scripts.checks.").split(".")[-1].replace("_", "-")
        specs.append(
            EntrypointSpec(
                module=module,
                name=name,
                kind=KIND_TOOL,
                group=FAMILY_GROUP,
                risk=RISK_READ_ONLY,
                help=_first_docstring_line(path),
                capture=_calls_parse_args(path),
                family=None if module in STANDALONE_CHECK_MODULES else FAMILY_CHECKS,
            )
        )
    return specs


def check_coverage(discovered: dict[str, Path], listed: set[str]) -> None:
    """Fail when a runnable module is neither listed, in the checks family, nor excluded."""
    missing = sorted(
        module for module in discovered if module not in listed and not module.startswith(EXCLUDED_MODULE_PREFIXES)
    )
    stale = sorted(module for module in listed if module not in discovered)
    problems: list[str] = []
    if missing:
        problems.append(f"runnable modules with no catalog entry: {missing}")
    if stale:
        problems.append(f"catalog entries whose module has no main(): {stale}")
    if problems:
        raise ValueError("; ".join(problems))


def _rows_for_spec(spec: EntrypointSpec) -> list[dict[str, Any]]:
    module = importlib.import_module(spec.module)
    invocation = f"python -m {spec.module}"
    schedule = None
    if spec.kind == KIND_JOB:
        definition = next((item for item in JOB_CATALOG.values() if item.module == spec.module), None)
        schedule = definition.schedule_kind if definition is not None else spec.cadence

    parser = capture_parser(module.main) if spec.capture and spec.module not in PARSERLESS_MODULES else None
    description = " ".join((parser.description or "").split()) if parser is not None else ""
    sub = subparsers_action(parser) if parser is not None else None

    if parser is not None and sub is not None:
        shared = describe_arguments(parser, SCOPE_GLOBAL)
        helps = subcommand_helps(sub)
        return [
            make_row(
                name=f"{spec.name} {sub_name}",
                kind=spec.kind,
                group=spec.group,
                risk=spec.sub_risks.get(sub_name, spec.risk),
                help_text=helps.get(sub_name) or description or spec.help,
                invocation=invocation,
                argv=["-m", spec.module],
                subcommand=sub_name,
                arguments=shared + describe_arguments(sub_parser),
                module=spec.module,
                schedule=schedule,
                runnable=f"{spec.name} {sub_name}" in RUNNABLE_TOOLS,
                family=spec.family or spec.name,
            )
            for sub_name, sub_parser in sub.choices.items()
        ]

    arguments = describe_arguments(parser) if parser is not None else []
    return [
        make_row(
            name=spec.name,
            kind=spec.kind,
            group=spec.group,
            risk=spec.risk,
            help_text=description or spec.help,
            invocation=invocation,
            argv=["-m", spec.module],
            subcommand=None,
            arguments=arguments,
            module=spec.module,
            schedule=schedule,
            runnable=spec.name in RUNNABLE_TOOLS,
            family=spec.family,
        )
    ]


def build_entrypoint_rows(repo_root: Path | None = None) -> list[dict[str, Any]]:
    """Return one row per runnable job and tool, in curated order."""
    root = repo_root or get_repo_root(__file__)
    discovered = discover_main_modules(root)
    family = _family_specs(discovered, root)
    specs = [*JOB_SPECS, *TOOL_SPECS, *family]
    check_coverage(discovered, {spec.module for spec in specs})
    rows: list[dict[str, Any]] = []
    for spec in specs:
        rows.extend(_rows_for_spec(spec))
    stale = RUNNABLE_TOOLS - {row["name"] for row in rows}
    if stale:
        raise ValueError(f"RUNNABLE_TOOLS lists entries that do not exist: {sorted(stale)}")
    used = {row["family"] for row in rows if row["family"] is not None}
    if used != FAMILIES.keys():
        raise ValueError(
            f"FAMILIES does not match the families in use: missing {sorted(used - FAMILIES.keys())}, "
            f"unused {sorted(FAMILIES.keys() - used)}"
        )
    return rows
