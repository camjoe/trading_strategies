from __future__ import annotations

import types

from trading.interfaces.cli.handlers.reporting_handlers import (
    handle_compare_strategies,
    handle_promotion_request_review,
    handle_promotion_review_action,
    handle_promotion_review_history,
    handle_promotion_status,
    handle_report,
    handle_snapshot,
    handle_snapshot_history,
)


def _parser():
    class _P:
        def error(self, msg: str) -> None:
            raise SystemExit(msg)

    return _P()


def test_handle_report_calls_account_report_dep() -> None:
    calls: list = []
    deps = {"account_report": lambda _conn, account: calls.append(account)}

    handle_report(
        object(),
        types.SimpleNamespace(account="alice"),
        _parser(),
        deps=deps,
        module_file="",
        db_path="",
    )

    assert calls == ["alice"]


def test_handle_snapshot_calls_snapshot_account_dep() -> None:
    calls: list = []
    deps = {"snapshot_account": lambda _conn, account, time: calls.append((account, time))}

    handle_snapshot(
        object(),
        types.SimpleNamespace(account="alice", time="2026-03-01T00:00:00"),
        _parser(),
        deps=deps,
        module_file="",
        db_path="",
    )

    assert calls == [("alice", "2026-03-01T00:00:00")]


def test_handle_promotion_status_calls_show_promotion_status_dep() -> None:
    calls: list = []
    deps = {
        "show_promotion_status": (
            lambda _conn, account, strategy: calls.append((account, strategy))
        )
    }

    handle_promotion_status(
        object(),
        types.SimpleNamespace(account="alice", strategy="trend_v1"),
        _parser(),
        deps=deps,
        module_file="",
        db_path="",
    )

    assert calls == [("alice", "trend_v1")]


def test_handle_promotion_request_review_calls_request_dep() -> None:
    calls: list = []
    deps = {
        "execute_promotion_review_request": (
            lambda _conn, **kwargs: (
                calls.append(kwargs)
                or types.SimpleNamespace(id=7, account_name_snapshot="alice", strategy_name="trend_v1", review_state="requested")
            )
        )
    }

    handle_promotion_request_review(
        object(),
        types.SimpleNamespace(
            account="alice",
            strategy="trend_v1",
            requested_by="cam",
            note="please review",
        ),
        _parser(),
        deps=deps,
        module_file="",
        db_path="",
    )

    assert calls == [
        {
            "account_name": "alice",
            "strategy_name": "trend_v1",
            "requested_by": "cam",
            "note": "please review",
        }
    ]


def test_handle_promotion_review_history_calls_history_dep() -> None:
    calls: list = []
    deps = {"show_promotion_review_history": lambda _conn, account, strategy, *, limit: calls.append((account, strategy, limit))}

    handle_promotion_review_history(
        object(),
        types.SimpleNamespace(account="alice", strategy="trend_v1", limit=5),
        _parser(),
        deps=deps,
        module_file="",
        db_path="",
    )

    assert calls == [("alice", "trend_v1", 5)]


def test_handle_promotion_review_action_calls_action_dep() -> None:
    calls: list = []
    deps = {
        "execute_promotion_review_action": (
            lambda _conn, **kwargs: calls.append(kwargs) or types.SimpleNamespace(id=7, review_state="approved")
        )
    }

    handle_promotion_review_action(
        object(),
        types.SimpleNamespace(review_id=7, action="approve", actor="cam", note="ship it"),
        _parser(),
        deps=deps,
        module_file="",
        db_path="",
    )

    assert calls == [
        {"review_id": 7, "action": "approve", "actor_name": "cam", "note": "ship it"}
    ]


def test_handle_snapshot_history_calls_show_snapshots_dep() -> None:
    calls: list = []
    deps = {"show_snapshots": lambda _conn, account, limit: calls.append((account, limit))}

    handle_snapshot_history(
        object(),
        types.SimpleNamespace(account="alice", limit=10),
        _parser(),
        deps=deps,
        module_file="",
        db_path="",
    )

    assert calls == [("alice", 10)]


def test_handle_compare_strategies_calls_compare_dep() -> None:
    calls: list = []
    deps = {"compare_strategies": lambda _conn, lookback: calls.append(lookback)}

    handle_compare_strategies(
        object(),
        types.SimpleNamespace(lookback=30),
        _parser(),
        deps=deps,
        module_file="",
        db_path="",
    )

    assert calls == [30]
