from __future__ import annotations

import json

from tests.support import check_daily_trader_health as module


def test_emit_human_readable_output(capsys) -> None:
    payload = module._make_payload(
        status="ok",
        message="All good",
        latest_log="/tmp/foo.log",
        latest_log_age_hours=2.5,
        sentinel_found=True,
    )

    module._emit(payload, as_json=False)

    out = capsys.readouterr().out
    assert "[OK] All good" in out
    assert "latest_log=/tmp/foo.log" in out
    assert "latest_log_age_hours=2.50" in out


def test_emit_json_output(capsys) -> None:
    payload = module._make_payload(
        status="fail",
        message="Stale",
        latest_log=None,
        latest_log_age_hours=None,
        sentinel_found=False,
    )

    module._emit(payload, as_json=True)

    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "fail"
    assert data["sentinel_found"] is False
