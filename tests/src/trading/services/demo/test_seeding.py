from __future__ import annotations

from trading.services.demo.seeding import seed_demo_database


def test_demo_seed_derives_daily_metrics_through_the_real_writer(conn) -> None:
    """The demo must produce daily_metrics via the production writer, not fabricate them.

    Guards the "demo consumes real code" property: the metrics come from the seeded
    equity curve + fills, so the demo can never display values the live system
    cannot compute — and the honestly-unavailable columns stay NULL.
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
    # Columns with no honest data source must be NULL, not fabricated (the old demo hardcoded them).
    assert all(row[2] is None for row in rows), "hit_rate must be NULL"
    assert all(row[3] is None for row in rows), "drawdown_pct must be NULL"
    assert all(row[4] is None for row in rows), "risk_adjusted_score must be NULL"
