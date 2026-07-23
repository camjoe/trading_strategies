"""Characterization tests for ``_run_books_for_account`` (auto_trading finding #1).

These lock the coordinator's *observable* behavior — stage ordering, the
kill-switch/throttle/anomaly branch outcomes, and broker-lifecycle cleanup —
before the runtime is reshaped. They deliberately fake every collaborator so
the assertions pin the orchestration wiring, not the collaborators' internals.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import trading.services.auto_trading.runtime as runtime_service
from tests.src.trading.services.auto_trading.factories import (
    FakeBroker,
    make_auto_trading_account,
    make_book_trade_candidate,
    make_feature_fetchers,
)
from trading.domain.exceptions import RuntimeTradeThrottleExceededError
from trading.models.execution.book_trade_intent import BookTradeIntent
from trading.models.execution.gate_result import GateResult
from trading.models.execution.submission_result import SubmissionResult

SNAPSHOT_TIME = "2026-03-14T14:00:00Z"
ACCOUNT_ID = 1


def _install(
    monkeypatch,
    *,
    intents,
    reconciliation_reasons=None,
    gate_result=None,
    submit_results=None,
    throttle_raises_before=None,
):
    """Patch every collaborator of ``_run_books_for_account`` and record calls.

    ``intents`` are the ``BookTradeCandidate`` list ``generate_book_trade_intents``
    returns. ``gate_result`` overrides the fake gate's output (default: approve all
    passed intents, no kill switches). ``submit_results`` is consumed one per book;
    ``throttle_raises_before`` makes the Nth throttle check raise.
    """
    recorder = SimpleNamespace(calls=[], persisted=[], submit_book_ids=[], throttle_count=0)

    monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: SNAPSHOT_TIME)
    monkeypatch.setattr(runtime_service, "row_expect_int", lambda _account, _key: ACCOUNT_ID)
    monkeypatch.setattr(runtime_service, "load_symbol_sector_map", lambda: {})

    def _rotation(_conn, *, account, decision_time):
        recorder.calls.append("rotation")

    monkeypatch.setattr(runtime_service, "_run_book_rotation_decisions", _rotation)

    def _generate(_conn, **_kwargs):
        recorder.calls.append("generate_intents")
        return list(intents)

    monkeypatch.setattr(runtime_service, "generate_book_trade_intents", _generate)

    def _mark(_conn, *, account_id, prices, as_of):
        recorder.calls.append("mark_to_market")

    monkeypatch.setattr(runtime_service, "mark_account_to_market", _mark)

    def _reconcile(_conn, *, account_id, now_iso):
        recorder.calls.append("reconcile")
        return list(reconciliation_reasons or [])

    monkeypatch.setattr(runtime_service, "reconcile_book_equity", _reconcile)

    class _FakeGate:
        def __init__(self, **_kwargs):
            pass

        def evaluate(self, _conn, *, account_id, intents):
            recorder.calls.append("gate.evaluate")
            if gate_result is not None:
                return gate_result
            return GateResult(approved_intents=list(intents))

    monkeypatch.setattr(runtime_service, "BookPreSubmitGate", _FakeGate)

    def _persist(_conn, *, account_id, snapshot_time, risk_decisions, kill_switch_reasons, summary):
        recorder.calls.append("persist_audit")
        recorder.persisted.append(
            SimpleNamespace(
                account_id=account_id,
                snapshot_time=snapshot_time,
                risk_decisions=risk_decisions,
                kill_switch_reasons=list(kill_switch_reasons),
                summary=summary,
            )
        )

    monkeypatch.setattr(runtime_service, "_persist_book_run_audit", _persist)

    def _throttle(_conn, *, trade_time_iso):
        recorder.throttle_count += 1
        recorder.calls.append("throttle_check")
        if throttle_raises_before is not None and recorder.throttle_count >= throttle_raises_before:
            raise RuntimeTradeThrottleExceededError("throttled")

    monkeypatch.setattr(runtime_service, "enforce_runtime_trade_throttles", _throttle)

    submit_iter = iter(submit_results or [])

    def _submit(_conn, *, book_id, account_id, intents, broker, gate, fee):
        recorder.calls.append(f"submit:{book_id}")
        recorder.submit_book_ids.append(book_id)
        try:
            return next(submit_iter)
        except StopIteration:
            return SubmissionResult(submitted_count=len(list(intents)))

    monkeypatch.setattr(runtime_service, "submit_book_intents", _submit)

    recorder.broker = FakeBroker()
    recorder.broker_factory = Mock(return_value=recorder.broker)
    return recorder


def _run(recorder, *, prices=None):
    return runtime_service._run_books_for_account(
        object(),
        account_name="acct",
        account=make_auto_trading_account(id=ACCOUNT_ID),
        universe=["AAPL"],
        prices=prices if prices is not None else {"AAPL": 100.0},
        iv_rank_proxy={},
        max_trades=5,
        fee=0.0,
        broker_factory=recorder.broker_factory,
        feature_fetchers=make_feature_fetchers(),
    )


def test_happy_path_submits_each_book_in_order_and_persists_audit(monkeypatch) -> None:
    recorder = _install(
        monkeypatch,
        intents=[make_book_trade_candidate(book_id=10), make_book_trade_candidate(book_id=20)],
    )

    submitted = _run(recorder)

    assert submitted == 2
    assert recorder.submit_book_ids == [10, 20]
    assert recorder.calls == [
        "rotation",
        "generate_intents",
        "mark_to_market",
        "reconcile",
        "gate.evaluate",
        "throttle_check",
        "submit:10",
        "throttle_check",
        "submit:20",
        "persist_audit",
    ]
    assert recorder.persisted[-1].summary["submitted_count"] == 2
    recorder.broker.disconnect.assert_called_once()


def test_no_intents_persists_empty_audit_without_touching_broker(monkeypatch) -> None:
    recorder = _install(monkeypatch, intents=[])

    submitted = _run(recorder)

    assert submitted == 0
    assert recorder.calls == ["rotation", "generate_intents", "persist_audit"]
    recorder.broker_factory.assert_not_called()
    assert recorder.persisted[-1].summary["submitted_count"] == 0
    assert recorder.persisted[-1].kill_switch_reasons == []


def test_reconciliation_mismatch_holds_run_before_broker(monkeypatch) -> None:
    recorder = _install(
        monkeypatch,
        intents=[make_book_trade_candidate(book_id=10)],
        reconciliation_reasons=[runtime_service.KILL_SWITCH_REASON_RECONCILIATION_MISMATCH],
    )

    submitted = _run(recorder)

    assert submitted == 0
    # The gate still evaluated, but the reconciliation kill switch holds the run
    # before any broker is opened or any book submits.
    assert "gate.evaluate" in recorder.calls
    assert not any(c.startswith("submit:") for c in recorder.calls)
    recorder.broker_factory.assert_not_called()
    assert runtime_service.KILL_SWITCH_REASON_RECONCILIATION_MISMATCH in recorder.persisted[-1].kill_switch_reasons


def test_stale_price_kill_switch_overrides_gate_approval(monkeypatch) -> None:
    approved = [
        BookTradeIntent(
            book_id=10,
            account_id=ACCOUNT_ID,
            strategy_id=None,
            symbol="AAPL",
            side="buy",
            qty=1.0,
            requested_price=100.0,
        )
    ]
    recorder = _install(
        monkeypatch,
        intents=[make_book_trade_candidate(book_id=10)],
        gate_result=GateResult(
            approved_intents=approved,
            kill_switch_reasons=[runtime_service.KILL_SWITCH_REASON_STALE_PRICE_DATA],
        ),
    )

    submitted = _run(recorder)

    # A stale-price kill switch holds the whole run even though the gate returned
    # an approved intent.
    assert submitted == 0
    assert not any(c.startswith("submit:") for c in recorder.calls)
    recorder.broker_factory.assert_not_called()
    assert runtime_service.KILL_SWITCH_REASON_STALE_PRICE_DATA in recorder.persisted[-1].kill_switch_reasons


def test_trade_throttle_stops_after_first_book(monkeypatch) -> None:
    recorder = _install(
        monkeypatch,
        intents=[make_book_trade_candidate(book_id=10), make_book_trade_candidate(book_id=20)],
        submit_results=[SubmissionResult(submitted_count=1)],
        throttle_raises_before=2,  # second book's throttle check raises
    )

    submitted = _run(recorder)

    assert submitted == 1
    assert recorder.submit_book_ids == [10]
    reasons = [d.get("reason_code") for d in recorder.persisted[-1].risk_decisions]
    assert runtime_service.RISK_REASON_TRADE_THROTTLE_EXCEEDED in reasons
    recorder.broker.disconnect.assert_called_once()


def test_broker_anomaly_stops_further_submission(monkeypatch) -> None:
    recorder = _install(
        monkeypatch,
        intents=[
            make_book_trade_candidate(book_id=10),
            make_book_trade_candidate(book_id=20),
            make_book_trade_candidate(book_id=30),
        ],
        submit_results=[
            SubmissionResult(submitted_count=1),
            SubmissionResult(kill_switch_reasons=[runtime_service.KILL_SWITCH_REASON_BROKER_API_ANOMALY]),
        ],
    )

    submitted = _run(recorder)

    # First book submits, second reports a broker anomaly and halts the loop;
    # the third book is never reached.
    assert submitted == 1
    assert recorder.submit_book_ids == [10, 20]
    assert runtime_service.KILL_SWITCH_REASON_BROKER_API_ANOMALY in recorder.persisted[-1].kill_switch_reasons
    recorder.broker.disconnect.assert_called_once()


def test_broker_disconnected_even_when_submission_raises(monkeypatch) -> None:
    recorder = _install(monkeypatch, intents=[make_book_trade_candidate(book_id=10)])
    monkeypatch.setattr(
        runtime_service,
        "submit_book_intents",
        Mock(side_effect=RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        _run(recorder)

    recorder.broker.disconnect.assert_called_once()
