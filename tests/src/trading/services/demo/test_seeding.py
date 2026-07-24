from __future__ import annotations

from trading.services.demo.seeding import seed_demo_database


def test_demo_seed_derives_daily_metrics_through_the_real_writer(conn) -> None:
    """The demo must produce daily_metrics via the production writer, not fabricate them.

    Guards the "demo consumes real code" property: the metrics come from the seeded
    equity curve + fills, so the demo can never display values the live system
    cannot compute — and the honestly-unavailable column stays NULL.
    """
    seed_demo_database(conn)

    rows = conn.execute(
        "SELECT return_pct, trade_count, hit_rate, drawdown_pct, risk_adjusted_score FROM daily_metrics"
    ).fetchall()
    assert rows, "demo should have written daily_metrics rows"

    # return_pct is derived from the seeded equity curve on days that have a prior snapshot.
    assert any(row[0] is not None for row in rows)
    # The seeded fills mean some days record trades.
    assert any((row[1] or 0) > 0 for row in rows)
    # risk_adjusted_score is a real derived column: the trailing writer fills it in
    # once the seeded equity curve has accumulated enough daily returns.
    assert any(row[4] is not None for row in rows), "risk_adjusted_score should be derived"
    # hit_rate is NULL because the seeded fills include no closing trades that realize
    # P&L; drawdown_pct is NULL because it has no honest data source at this grain.
    # Neither is fabricated (the old demo hardcoded both).
    assert all(row[2] is None for row in rows), "hit_rate must be NULL"
    assert all(row[3] is None for row in rows), "drawdown_pct must be NULL"
