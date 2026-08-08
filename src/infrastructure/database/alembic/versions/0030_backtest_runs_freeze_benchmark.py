"""Freeze a backtest run's benchmark on the run row.

Revision ID: 0030
Revises: 0029

The benchmark return was computed while a run executed and then discarded, so
every reader recomputed it. Two problems followed.

The recompute resolved the benchmark ticker through ``accounts.benchmark_ticker``
— the account's *current* value, not the one the run used. Changing an account's
benchmark silently re-benchmarked every past run against a ticker it never
traded against, and reported alpha those runs never had.

It also needed a ``MarketDataProvider`` at read time. The report path injected
one; the leaderboard path did not, so its ``benchmark_return_pct`` and
``alpha_pct`` were always empty.

Both columns are nullable. Rows written before this revision have no stored
value and cannot be backfilled here: the return depends on market data, which a
self-contained revision cannot fetch. A run whose benchmark has no history over
its window is also legitimately null. Readers treat null as "no benchmark", the
same as a failed lookup.

Alpha stays derived (total return minus benchmark return) rather than stored —
it is a subtraction of two values the row already has.
"""

from __future__ import annotations

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE backtest_runs ADD COLUMN benchmark_ticker TEXT")
    op.execute("ALTER TABLE backtest_runs ADD COLUMN benchmark_return_pct REAL")


def downgrade() -> None:
    # Restores schema shape; discarded values come back from backups, not downgrades.
    with op.batch_alter_table("backtest_runs") as batch:
        batch.drop_column("benchmark_return_pct")
        batch.drop_column("benchmark_ticker")
