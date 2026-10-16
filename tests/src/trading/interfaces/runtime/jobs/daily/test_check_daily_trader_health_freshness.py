from __future__ import annotations

import contextlib
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from tests.src.trading.interfaces.runtime.jobs.loaders import check_daily_trader_health as module
from tests.support.books import build_book_env
from tests.support.repositories import insert_repository_account

TODAY = dt.date(2026, 10, 16)


@pytest.fixture
def database(conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> sqlite3.Connection:
    monkeypatch.setattr(module, "utc_today", lambda: TODAY)
    monkeypatch.setattr(module, "db_session", lambda: contextlib.nullcontext(conn))
    return conn


def _args(*extra: str):
    monkeypatch_argv = ["check_daily_trader_health", *extra]
    old, sys.argv = sys.argv, monkeypatch_argv
    try:
        return module.parse_args()
    finally:
        sys.argv = old


def _snapshot(conn: sqlite3.Connection, name: str, date: str) -> None:
    build_book_env(conn, account_name=name, snapshot_time=f"{date}T13:59:00Z")


def test_fresh_accounts_are_ok(database: sqlite3.Connection) -> None:
    _snapshot(database, "fresh", "2026-10-16")

    assert module._check_freshness(_args())["status"] == "ok"


def test_a_stale_account_warns_and_a_very_stale_one_fails(database: sqlite3.Connection) -> None:
    _snapshot(database, "two_days", "2026-10-14")
    assert module._check_freshness(_args()) == {
        "status": "warn",
        "message": "1 account(s) without a recent equity snapshot: two_days (last snapshot 2026-10-14, 2 weekdays ago)",
        "accounts": ["two_days (last snapshot 2026-10-14, 2 weekdays ago)"],
    }

    _snapshot(database, "five_days", "2026-10-09")
    result = module._check_freshness(_args())
    assert result["status"] == "fail"
    assert [name.split(" ")[0] for name in result["accounts"]] == ["five_days", "two_days"]


def test_an_account_never_snapshotted_is_named_as_a_warning(database: sqlite3.Connection) -> None:
    insert_repository_account(database, name="brand_new")

    result = module._check_freshness(_args())

    assert result["status"] == "warn"
    assert result["accounts"] == ["brand_new (never snapshotted)"]


def test_thresholds_come_from_the_command_line(database: sqlite3.Connection) -> None:
    _snapshot(database, "two_days", "2026-10-14")

    assert (
        module._check_freshness(_args("--fail-after-weekdays", "2", "--warn-after-weekdays", "1"))["status"] == "fail"
    )


def test_a_check_that_cannot_run_is_a_failure_not_a_pass(database: sqlite3.Connection) -> None:
    _snapshot(database, "from_the_future", "2026-10-20")

    result = module._check_freshness(_args())

    assert result["status"] == "fail"
    assert "could not run" in result["message"] and "from_the_future" in result["message"]


def test_bad_thresholds_are_rejected_before_any_check(monkeypatch: pytest.MonkeyPatch, job_root: Path, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["x", "--repo-root", str(job_root), "--warn-after-weekdays", "6"])

    assert module.main() == 2
    assert "--warn-after-weekdays" in capsys.readouterr().err


def _healthy_log(job_root: Path) -> None:
    (job_root / "local" / "logs" / "daily_paper_trading_20260417_120000.log").write_text(
        f"{module.COMPLETE_SENTINEL}\n", encoding="utf-8"
    )


def _run(monkeypatch: pytest.MonkeyPatch, job_root: Path, *extra: str) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "x",
            "--repo-root",
            str(job_root),
            "--max-age-hours",
            "9999",
            "--notify-webhook-url",
            "https://e.test",
            *extra,
        ],
    )
    return module.main()


def test_a_failing_freshness_check_exits_1_and_sends_one_digest(
    monkeypatch: pytest.MonkeyPatch, job_root: Path
) -> None:
    _healthy_log(job_root)
    sent: list[dict[str, object]] = []
    monkeypatch.setattr(module, "notify_runtime_event", lambda **kwargs: sent.append(kwargs) or True)
    monkeypatch.setattr(
        module,
        "_check_freshness",
        lambda _a: {"status": "fail", "message": "2 account(s) stale", "accounts": ["a", "b"]},
    )

    assert _run(monkeypatch, job_root) == 1
    assert [(call["event"], call["status"]) for call in sent] == [("account-freshness", "fail")]
    assert sent[0]["details"] == {"accounts": ["a", "b"]}


def test_a_warning_sends_a_digest_but_keeps_exit_0(monkeypatch: pytest.MonkeyPatch, job_root: Path) -> None:
    _healthy_log(job_root)
    sent: list[dict[str, object]] = []
    monkeypatch.setattr(module, "notify_runtime_event", lambda **kwargs: sent.append(kwargs) or True)
    monkeypatch.setattr(
        module, "_check_freshness", lambda _a: {"status": "warn", "message": "1 stale", "accounts": ["a"]}
    )

    assert _run(monkeypatch, job_root) == 0
    assert [(call["event"], call["status"]) for call in sent] == [("account-freshness", "warn")]


def test_a_failing_log_check_still_fails_when_accounts_are_fresh(
    monkeypatch: pytest.MonkeyPatch, job_root: Path, fresh_accounts: None
) -> None:
    (job_root / "local" / "logs" / "daily_paper_trading_20260417_120000.log").write_text("partial\n", encoding="utf-8")
    monkeypatch.setattr(module, "notify_runtime_event", lambda **kwargs: True)

    assert _run(monkeypatch, job_root) == 1


def test_json_output_keeps_the_log_fields_and_adds_freshness(
    monkeypatch: pytest.MonkeyPatch, job_root: Path, fresh_accounts: None, capsys
) -> None:
    _healthy_log(job_root)

    assert _run(monkeypatch, job_root, "--json") == 0

    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "ok" and data["sentinel_found"] is True
    assert data["freshness"]["status"] == "ok"


@pytest.mark.parametrize("freshness_status", ["warn", "fail"])
@pytest.mark.parametrize("log", ["missing", "no_sentinel"])
def test_a_failing_log_check_and_a_stale_account_both_alert(
    monkeypatch: pytest.MonkeyPatch, job_root: Path, log: str, freshness_status: str
) -> None:
    if log == "no_sentinel":
        (job_root / "local" / "logs" / "daily_paper_trading_20260417_120000.log").write_text(
            "partial\n", encoding="utf-8"
        )
    sent: list[dict[str, object]] = []
    monkeypatch.setattr(module, "notify_runtime_event", lambda **kwargs: sent.append(kwargs) or True)
    monkeypatch.setattr(
        module, "_check_freshness", lambda _a: {"status": freshness_status, "message": "1 stale", "accounts": ["a"]}
    )

    assert _run(monkeypatch, job_root) == 1
    assert [(call["event"], call["status"]) for call in sent] == [
        ("daily-trader-health", "fail"),
        ("account-freshness", freshness_status),
    ]


def test_a_database_that_cannot_be_opened_fails_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    def _broken_session():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(module, "db_session", _broken_session)

    result = module._check_freshness(_args())

    assert result["status"] == "fail"
    assert "OperationalError: database is locked" in result["message"]


def test_text_output_shows_the_freshness_line(monkeypatch: pytest.MonkeyPatch, job_root: Path, capsys) -> None:
    _healthy_log(job_root)
    monkeypatch.setattr(module, "notify_runtime_event", lambda **kwargs: True)
    monkeypatch.setattr(
        module, "_check_freshness", lambda _a: {"status": "warn", "message": "1 stale", "accounts": ["a"]}
    )

    _run(monkeypatch, job_root)

    assert "[WARN] 1 stale" in capsys.readouterr().out


@pytest.mark.parametrize(("warn", "fail"), [("0", "5"), ("-1", "3"), ("3", "2")])
def test_thresholds_outside_the_allowed_range_exit_2(
    monkeypatch: pytest.MonkeyPatch, job_root: Path, warn: str, fail: str
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["x", "--repo-root", str(job_root), "--warn-after-weekdays", warn, "--fail-after-weekdays", fail]
    )

    assert module.main() == 2


def test_main_names_a_stale_account_from_the_database(
    monkeypatch: pytest.MonkeyPatch, job_root: Path, database: sqlite3.Connection
) -> None:
    _healthy_log(job_root)
    _snapshot(database, "stale_account", "2026-10-09")
    sent: list[dict[str, object]] = []
    monkeypatch.setattr(module, "notify_runtime_event", lambda **kwargs: sent.append(kwargs) or True)

    assert _run(monkeypatch, job_root) == 1
    assert sent[0]["event"] == "account-freshness" and "stale_account" in str(sent[0]["message"])
