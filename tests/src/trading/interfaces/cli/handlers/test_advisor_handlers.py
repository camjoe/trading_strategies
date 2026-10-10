from __future__ import annotations

import types

import pytest

import trading.interfaces.cli.handlers.advisor_handlers as module
from tests.src.trading.interfaces.cli.handlers.helpers import fake_parser, make_ctx, patch_services
from trading.interfaces.cli.handlers.advisor_handlers import (
    handle_advisor_digest,
    handle_advisor_record,
    handle_advisor_score,
    handle_advisor_scorecard,
)
from trading.models.advisor import AdvisorDigest


def _record_args(**overrides):
    base = {
        "account": "acct",
        "type": "hold",
        "rationale": "waiting for evidence",
        "decided_by": "agent",
        "book": None,
        "strategy": None,
        "alternative": None,
        "note": [],
        "experiment_id": None,
        "promotion_review_id": None,
        "window_days": 21,
    }
    base.update(overrides)
    return types.SimpleNamespace(**base)


def test_record_passes_parsed_notes_and_reports_the_id(capsys, monkeypatch) -> None:
    calls: dict = {}

    def _record(_conn, **kwargs):
        calls.update(kwargs)
        return 7

    patch_services(monkeypatch, module, record_decision=_record)
    handle_advisor_record(
        object(),
        _record_args(note=["source=digest", " gap = stale backtest "]),
        fake_parser(),
        ctx=make_ctx(),
    )

    assert calls["notes"] == {"source": "digest", "gap": "stale backtest"}
    assert calls["decision_type"] == "hold"
    assert "Recorded decision #7 (hold)" in capsys.readouterr().out


@pytest.mark.parametrize("bad_note", ["no_separator", "=value_without_key"])
def test_record_rejects_a_malformed_note(monkeypatch, bad_note) -> None:
    patch_services(monkeypatch, module, record_decision=lambda _conn, **_kwargs: 1)
    with pytest.raises(SystemExit, match="KEY=VALUE"):
        handle_advisor_record(object(), _record_args(note=[bad_note]), fake_parser(), ctx=make_ctx())


def test_record_surfaces_a_service_validation_error(monkeypatch) -> None:
    def _record(_conn, **_kwargs):
        raise ValueError("A decision needs a rationale.")

    patch_services(monkeypatch, module, record_decision=_record)
    with pytest.raises(SystemExit, match="needs a rationale"):
        handle_advisor_record(object(), _record_args(), fake_parser(), ctx=make_ctx())


def test_digest_parses_as_of_and_prints_the_rendered_lines(capsys, monkeypatch) -> None:
    calls: dict = {}

    def _build(_conn, **kwargs):
        calls.update(kwargs)
        return AdvisorDigest(generated_at="2026-10-02T00:00:00Z", as_of_date="2026-10-01", accounts=[])

    patch_services(monkeypatch, module, build_advisor_digest=_build)
    handle_advisor_digest(
        object(),
        types.SimpleNamespace(account=None, as_of="2026-10-01"),
        fake_parser(),
        ctx=make_ctx(),
    )

    assert str(calls["as_of"]) == "2026-10-01"
    output = capsys.readouterr().out
    assert "Advisor digest as of 2026-10-01" in output
    assert "No accounts." in output


def test_digest_rejects_a_malformed_as_of(monkeypatch) -> None:
    patch_services(monkeypatch, module, build_advisor_digest=lambda _conn, **_kwargs: None)
    with pytest.raises(SystemExit, match="Invalid isoformat"):
        handle_advisor_digest(
            object(),
            types.SimpleNamespace(account=None, as_of="10/01/2026"),
            fake_parser(),
            ctx=make_ctx(),
        )


def test_score_binds_the_provider_and_prints_the_results(capsys, monkeypatch) -> None:
    calls: dict = {}

    def _score(_conn, **kwargs):
        calls.update(kwargs)
        return []

    patch_services(monkeypatch, module, score_due_decisions=_score)
    ctx = make_ctx()
    handle_advisor_score(object(), types.SimpleNamespace(account="acct", as_of=None), fake_parser(), ctx=ctx)

    assert calls["account_name"] == "acct"
    assert calls["run_backtest_fn"].keywords == {"provider": ctx.provider}
    assert "No decisions are due for scoring." in capsys.readouterr().out


def test_scorecard_passes_the_grouping_and_prints_the_card(capsys, monkeypatch) -> None:
    from trading.models.advisor import Scorecard

    calls: dict = {}

    def _build(_conn, **kwargs):
        calls.update(kwargs)
        return Scorecard(
            generated_at="2026-10-03T00:00:00Z", group_by="regime", groups=[], rankable_count=0, leader=None
        )

    patch_services(monkeypatch, module, build_advisor_scorecard=_build)
    handle_advisor_scorecard(object(), types.SimpleNamespace(account=None, by="regime"), fake_parser(), ctx=make_ctx())

    assert calls == {"account_name": None, "group_by": "regime"}
    assert "No scored decisions yet." in capsys.readouterr().out
