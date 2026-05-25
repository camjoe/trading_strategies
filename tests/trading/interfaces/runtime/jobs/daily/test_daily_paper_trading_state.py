from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import trading.interfaces.runtime.jobs.daily.paper_trading_dag as dag_module
from tests.trading.interfaces.runtime.jobs.loaders import daily_paper_trading as module


def test_already_completed_today_returns_false_when_no_logs(tmp_path: Path) -> None:
    assert module.already_completed_today(tmp_path, today=dt.date(2026, 3, 30)) is False


def test_already_completed_today_returns_true_when_sentinel_found(tmp_path: Path) -> None:
    today = dt.date(2026, 3, 30)
    log = tmp_path / f"daily_paper_trading_{today.strftime('%Y%m%d')}_120000.log"
    log.write_text(f"run\n{module.COMPLETE_SENTINEL}\n", encoding="utf-8")
    assert module.already_completed_today(tmp_path, today=today) is True


def test_already_completed_today_returns_false_when_sentinel_absent(tmp_path: Path) -> None:
    today = dt.date(2026, 3, 30)
    log = tmp_path / f"daily_paper_trading_{today.strftime('%Y%m%d')}_120000.log"
    log.write_text("partial run\n", encoding="utf-8")
    assert module.already_completed_today(tmp_path, today=today) is False


def test_already_completed_today_uses_todays_date_tag_by_default(tmp_path: Path) -> None:
    today = dt.date.today()
    log = tmp_path / f"daily_paper_trading_{today.strftime('%Y%m%d')}_000000.log"
    log.write_text(f"{module.COMPLETE_SENTINEL}\n", encoding="utf-8")
    assert module.already_completed_today(tmp_path) is True


def test_group_accounts_by_caps_single_group() -> None:
    caps = {"a": (1, 5), "b": (1, 5)}
    result = module.group_accounts_by_caps(["a", "b"], caps)
    assert result == {(1, 5): ["a", "b"]}


def test_group_accounts_by_caps_multiple_groups() -> None:
    caps = {"a": (1, 5), "b": (1, 11), "c": (1, 5)}
    result = module.group_accounts_by_caps(["a", "b", "c"], caps)
    assert result[(1, 5)] == ["a", "c"]
    assert result[(1, 11)] == ["b"]


def test_group_accounts_by_caps_preserves_insertion_order_within_group() -> None:
    caps = {"z": (1, 5), "a": (1, 5), "m": (1, 5)}
    result = module.group_accounts_by_caps(["z", "a", "m"], caps)
    assert result[(1, 5)] == ["z", "a", "m"]


def test_group_accounts_by_caps_empty_accounts_returns_empty() -> None:
    assert module.group_accounts_by_caps([], {}) == {}


def test_step_result_raises_for_unknown_step_id() -> None:
    with pytest.raises(ValueError, match="Unknown DAG step id"):
        dag_module.step_result(dag_module.new_step_results(), "missing_step")


def test_failed_step_id_returns_none_when_all_steps_pending() -> None:
    assert dag_module.failed_step_id(dag_module.new_step_results()) is None
