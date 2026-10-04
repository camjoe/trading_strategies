from __future__ import annotations

from trading.interfaces.runtime.jobs.daily.paper_trading import workflow
from trading.interfaces.runtime.jobs.daily.paper_trading.dag import new_step_results, step_result


def test_build_run_summary_rolls_up_step_counts() -> None:
    step_results = new_step_results()
    step_result(step_results, "06_pretrade_risk_gate").details = {
        "total_decisions": 6,
        "blocked": 2,
        "rescaled": 1,
        "kill_switch_accounts": ["momentum"],
    }
    step_result(step_results, "07_submit_ibkr_orders").details = {
        "accounts": [
            {"order_count": 3, "accepted_count": 2, "turned_away_count": 1},
            {"order_count": 2, "accepted_count": 2, "turned_away_count": 0},
        ]
    }

    summary = workflow.build_run_summary(
        step_results,
        accounts=["momentum", "meanrev"],
        kill_switch_accounts=["momentum"],
    )

    assert summary["accounts"] == 2
    assert summary["orders_submitted"] == 5
    assert summary["orders_accepted"] == 4
    assert summary["orders_turned_away"] == 1
    assert summary["decisions_total"] == 6
    assert summary["decisions_blocked"] == 2
    assert summary["decisions_rescaled"] == 1
    assert summary["kill_switch_count"] == 1
    # Log counts are wired in and always present as ints (values depend on the run).
    for key in ("log_warnings", "log_errors", "log_critical"):
        assert isinstance(summary[key], int)


def test_build_run_summary_is_all_zero_when_steps_did_not_run() -> None:
    # A run that failed before step 06/07 leaves those steps with empty details;
    # the summary must read them as zero rather than raising.
    summary = workflow.build_run_summary(
        new_step_results(),
        accounts=["momentum"],
        kill_switch_accounts=[],
    )

    assert summary["orders_submitted"] == 0
    assert summary["decisions_total"] == 0
    assert summary["kill_switch_count"] == 0
