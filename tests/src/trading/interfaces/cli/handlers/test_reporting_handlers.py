from __future__ import annotations

import types

import trading.interfaces.cli.handlers.reporting_handlers as module
from tests.src.trading.interfaces.cli.handlers.helpers import fake_parser, make_ctx, patch_services
from trading.interfaces.cli.handlers.reporting_handlers import (
    handle_compare_strategies,
    handle_parameters,
    handle_portfolio_concentration,
    handle_portfolio_exposure,
    handle_promotion_request_review,
    handle_promotion_review_action,
    handle_promotion_review_history,
    handle_promotion_status,
    handle_report,
    handle_snapshot,
    handle_snapshot_history,
)


def test_handle_report_calls_account_report_dep(monkeypatch) -> None:
    calls: list = []
    patch_services(monkeypatch, module, account_report=lambda _conn, account, **_kw: calls.append(account))

    handle_report(
        object(),
        types.SimpleNamespace(account="alice"),
        fake_parser(),
        ctx=make_ctx(),
    )

    assert calls == ["alice"]


def test_handle_snapshot_calls_snapshot_account_dep(monkeypatch) -> None:
    calls: list = []
    patch_services(
        monkeypatch, module, snapshot_account=lambda _conn, account, time, **_kw: calls.append((account, time))
    )

    handle_snapshot(
        object(),
        types.SimpleNamespace(account="alice", time="2026-03-01T00:00:00"),
        fake_parser(),
        ctx=make_ctx(),
    )

    assert calls == [("alice", "2026-03-01T00:00:00")]


def test_handle_promotion_status_calls_show_promotion_status_dep(monkeypatch) -> None:
    calls: list = []
    patch_services(
        monkeypatch, module, show_promotion_status=(lambda _conn, account, strategy: calls.append((account, strategy)))
    )

    handle_promotion_status(
        object(),
        types.SimpleNamespace(account="alice", strategy="trend_v1"),
        fake_parser(),
        ctx=make_ctx(),
    )

    assert calls == [("alice", "trend_v1")]


def test_handle_promotion_request_review_calls_request_dep(monkeypatch) -> None:
    calls: list = []
    patch_services(
        monkeypatch,
        module,
        execute_promotion_review_request=(
            lambda _conn, **kwargs: (
                calls.append(kwargs)
                or types.SimpleNamespace(
                    id=7, account_name_snapshot="alice", strategy_name="trend_v1", review_state="requested"
                )
            )
        ),
    )

    handle_promotion_request_review(
        object(),
        types.SimpleNamespace(
            account="alice",
            strategy="trend_v1",
            requested_by="cam",
            note="please review",
        ),
        fake_parser(),
        ctx=make_ctx(),
    )

    assert calls == [
        {
            "account_name": "alice",
            "strategy_name": "trend_v1",
            "requested_by": "cam",
            "note": "please review",
        }
    ]


def test_handle_promotion_review_history_calls_history_dep(monkeypatch) -> None:
    calls: list = []
    patch_services(
        monkeypatch,
        module,
        show_promotion_review_history=lambda _conn, account, strategy, *, limit: calls.append(
            (account, strategy, limit)
        ),
    )

    handle_promotion_review_history(
        object(),
        types.SimpleNamespace(account="alice", strategy="trend_v1", limit=5),
        fake_parser(),
        ctx=make_ctx(),
    )

    assert calls == [("alice", "trend_v1", 5)]


def test_handle_promotion_review_action_calls_action_dep(monkeypatch) -> None:
    calls: list = []
    patch_services(
        monkeypatch,
        module,
        execute_promotion_review_action=(
            lambda _conn, **kwargs: calls.append(kwargs) or types.SimpleNamespace(id=7, review_state="approved")
        ),
    )

    handle_promotion_review_action(
        object(),
        types.SimpleNamespace(review_id=7, action="approve", actor="cam", note="ship it"),
        fake_parser(),
        ctx=make_ctx(),
    )

    assert calls == [{"review_id": 7, "action": "approve", "actor_name": "cam", "note": "ship it"}]


def test_handle_snapshot_history_calls_show_snapshots_dep(monkeypatch) -> None:
    calls: list = []
    patch_services(monkeypatch, module, show_snapshots=lambda _conn, account, limit: calls.append((account, limit)))

    handle_snapshot_history(
        object(),
        types.SimpleNamespace(account="alice", limit=10),
        fake_parser(),
        ctx=make_ctx(),
    )

    assert calls == [("alice", 10)]


def test_handle_portfolio_exposure_calls_show_dep(monkeypatch) -> None:
    calls: list = []
    conn = object()
    patch_services(monkeypatch, module, show_portfolio_exposure=lambda passed_conn: calls.append(passed_conn))

    handle_portfolio_exposure(
        conn,
        types.SimpleNamespace(),
        fake_parser(),
        ctx=make_ctx(),
    )

    assert calls == [conn]


def test_handle_portfolio_concentration_calls_show_dep(monkeypatch) -> None:
    calls: list = []
    conn = object()
    patch_services(monkeypatch, module, show_portfolio_concentration=lambda passed_conn: calls.append(passed_conn))

    handle_portfolio_concentration(
        conn,
        types.SimpleNamespace(),
        fake_parser(),
        ctx=make_ctx(),
    )

    assert calls == [conn]


def test_handle_parameters_calls_show_dep_with_account_filter(monkeypatch) -> None:
    calls: list = []
    conn = object()
    patch_services(
        monkeypatch, module, show_parameters=lambda passed_conn, account: calls.append((passed_conn, account))
    )

    handle_parameters(
        conn,
        types.SimpleNamespace(account="alice"),
        fake_parser(),
        ctx=make_ctx(),
    )

    assert calls == [(conn, "alice")]


def test_handle_compare_strategies_calls_compare_dep(monkeypatch) -> None:
    calls: list = []
    patch_services(monkeypatch, module, compare_strategies=lambda _conn, lookback, **_kw: calls.append(lookback))

    handle_compare_strategies(
        object(),
        types.SimpleNamespace(lookback=30),
        fake_parser(),
        ctx=make_ctx(),
    )

    assert calls == [30]
