from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

RUN_ALL_ACCOUNTS_ARGS: tuple[str, ...] = ("--accounts", "all")

DAILY_PAPER_TRADING_MODULE = "trading.interfaces.runtime.jobs.daily.paper_trading"
DAILY_PAPER_TRADING_REPORTING_MODULE = "trading.interfaces.runtime.jobs.daily.paper_trading.reporting"
DAILY_PAPER_TRADING_WORKFLOW_MODULE = "trading.interfaces.runtime.jobs.daily.paper_trading.workflow"
CHECK_DAILY_TRADER_HEALTH_MODULE = "trading.interfaces.runtime.jobs.daily.trader_health"
MANAGE_JOB_SCHEDULES_MODULE = "trading.interfaces.runtime.scheduling.manage_job_schedules"
RUN_AUTO_TRADES_MODULE = "trading.interfaces.runtime.jobs.daily.paper_trading.run_auto_trades"
DAILY_CHALLENGER_SHADOW_EVAL_MODULE = "trading.interfaces.runtime.jobs.daily.challenger_shadow_eval"


def load_runtime_job(module_name: str):
    return importlib.import_module(module_name)


def load_daily_paper_trading():
    return load_runtime_job(DAILY_PAPER_TRADING_MODULE)


def load_check_daily_trader_health():
    return load_runtime_job(CHECK_DAILY_TRADER_HEALTH_MODULE)


def load_manage_job_schedules():
    return load_runtime_job(MANAGE_JOB_SCHEDULES_MODULE)


def load_run_auto_trades():
    return load_runtime_job(RUN_AUTO_TRADES_MODULE)


def load_daily_challenger_shadow_eval():
    return load_runtime_job(DAILY_CHALLENGER_SHADOW_EVAL_MODULE)


daily_paper_trading = load_daily_paper_trading()
check_daily_trader_health = load_check_daily_trader_health()
manage_job_schedules = load_manage_job_schedules()
run_auto_trades = load_run_auto_trades()
daily_challenger_shadow_eval = load_daily_challenger_shadow_eval()


def make_manage_job_schedules_args(**overrides):
    defaults = {
        "daily_paper_trading_time": "",
        "daily_paper_trading_task_name": r"Trading\DailyPaperTrading",
        "daily_paper_trading_fallback_time": "",
        "daily_paper_trading_fallback_task_name": r"Trading\DailyPaperTradingFallback",
        "daily_challenger_shadow_eval_time": "",
        "daily_challenger_shadow_eval_task_name": r"Trading\DailyChallengerShadowEval",
        "enable_daily_challenger_shadow_eval": False,
        "auto_shadow_eval_from_daily_paper": False,
        "shadow_eval_lead_minutes": 20,
        "health_check_time": "",
        "health_check_task_name": r"Trading\DailyTraderHealthCheck",
        "health_check_max_age_hours": 24.0,
        "weekly_db_backup_time": "",
        "weekly_db_backup_day_of_week": "Sunday",
        "weekly_db_backup_task_name": r"Trading\WeeklyDbBackup",
        "unregister": False,
        "dry_run": False,
        "python": "/tmp/.venv/bin/python",
        "scheduler": "auto",
        "wake_system": True,
        "env_file": "",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_run_auto_trades_args(**overrides):
    defaults = {
        "max_trades": 1,
        "seed": None,
        "accounts": "acct1",
        "tickers_file": "src/infrastructure/config/trade_universe.txt",
        "fee": 0.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_daily_challenger_shadow_eval_args(**overrides):
    defaults = {
        "accounts": "all",
        "force_run": False,
        "run_source": "test-run",
        "enable_run": True,
        "rolling_window_days": 30,
        "repo_root": ".",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def run_runtime_job_main(monkeypatch, tmp_path: Path, module_name: str, argv: list[str]) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        [module_name.rsplit(".", 1)[-1]] + argv + ["--repo-root", str(tmp_path)],
    )
    (tmp_path / "local" / "logs").mkdir(parents=True, exist_ok=True)
    return load_runtime_job(module_name).main()


def run_runtime_job_with_args(
    monkeypatch,
    tmp_path: Path,
    module_name: str,
    args: tuple[str, ...] = RUN_ALL_ACCOUNTS_ARGS,
) -> int:
    return run_runtime_job_main(monkeypatch, tmp_path, module_name, list(args))


def write_completed_runtime_log(
    tmp_path: Path,
    *,
    filename_prefix: str,
    tag: str,
    sentinel: str,
    timestamp: str | None = None,
) -> Path:
    logs_dir = tmp_path / "local" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    resolved_timestamp = timestamp or dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"{filename_prefix}_{tag}_{resolved_timestamp}.log"
    log_path.write_text(f"{sentinel}\n", encoding="utf-8")
    return log_path


def load_single_artifact_json(artifacts_dir: Path, pattern: str) -> dict[str, object]:
    artifacts = list(artifacts_dir.glob(pattern))
    assert len(artifacts) == 1
    return json.loads(artifacts[0].read_text(encoding="utf-8"))


def set_runtime_eligible_accounts(monkeypatch, module_name: str, accounts: list[str]) -> None:
    monkeypatch.setattr(
        f"{module_name}.load_runtime_eligible_account_names",
        lambda: list(accounts),
    )


def stub_runtime_job_basics(
    monkeypatch,
    module,
    *,
    runtime_accounts: list[str] | None = None,
    db_conn=None,
    account_lookup: Callable[[str], object | None] | None = None,
    books_for_account: list[object] | None = None,
) -> SimpleNamespace:
    """Apply common runtime-job test stubs for DB/account surfaces.

    ``books_for_account`` items are either ``(book, assignment)`` tuples or plain
    dicts of book fields (paired with ``None`` assignment); they stub the module's
    ``list_report_books``.

    Returns a SimpleNamespace with:
      - conn: the stubbed DB connection
      - books: the stubbed (book, assignment) pairs (if patched)
    """
    import infrastructure.database.connection as db_init
    import trading.interfaces.runtime.jobs.job_runner._core as job_runner

    resolved_accounts = list(runtime_accounts or ["acct1"])
    resolved_conn = db_conn or SimpleNamespace(close=lambda: None)
    lookup = account_lookup or (lambda name: SimpleNamespace(id=1, name=name))

    # Migrated jobs (ADR 006) open the DB via the shared `db_session`
    # (infrastructure.database.connection.ensure_db); legacy jobs call `ensure_db` on
    # their own module. Patch whichever targets define it so both styles work.
    for target in (module, job_runner, db_init):
        if hasattr(target, "ensure_db"):
            monkeypatch.setattr(target, "ensure_db", lambda: resolved_conn)
    for target in (module, job_runner):
        if hasattr(target, "load_runtime_eligible_account_names"):
            monkeypatch.setattr(target, "load_runtime_eligible_account_names", lambda: list(resolved_accounts))
    if hasattr(module, "find_account"):
        monkeypatch.setattr(module, "find_account", lambda conn, name: lookup(name))

    book_pairs = None

    if books_for_account is not None and hasattr(module, "list_report_books"):
        book_pairs = [
            (SimpleNamespace(**item), None) if isinstance(item, dict) else item for item in books_for_account
        ]
        monkeypatch.setattr(module, "list_report_books", lambda conn, *, account_id: list(book_pairs))

    return SimpleNamespace(conn=resolved_conn, books=book_pairs)


__all__ = [
    "CHECK_DAILY_TRADER_HEALTH_MODULE",
    "MANAGE_JOB_SCHEDULES_MODULE",
    "RUN_ALL_ACCOUNTS_ARGS",
    "DAILY_PAPER_TRADING_MODULE",
    "RUN_AUTO_TRADES_MODULE",
    "DAILY_CHALLENGER_SHADOW_EVAL_MODULE",
    "check_daily_trader_health",
    "manage_job_schedules",
    "daily_paper_trading",
    "run_auto_trades",
    "daily_challenger_shadow_eval",
    "load_check_daily_trader_health",
    "load_manage_job_schedules",
    "load_daily_paper_trading",
    "load_run_auto_trades",
    "load_daily_challenger_shadow_eval",
    "load_runtime_job",
    "load_single_artifact_json",
    "make_daily_challenger_shadow_eval_args",
    "make_manage_job_schedules_args",
    "make_run_auto_trades_args",
    "run_runtime_job_main",
    "run_runtime_job_with_args",
    "set_runtime_eligible_accounts",
    "stub_runtime_job_basics",
    "write_completed_runtime_log",
]
