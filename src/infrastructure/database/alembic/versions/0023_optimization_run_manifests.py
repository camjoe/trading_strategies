"""Add optimization_run_manifests for walk-forward optimizer provenance.

Revision ID: 0023
Revises: 0022

Freezes one provenance manifest per ``backtest-optimize`` run (1:1 with
``optimization_experiments``): the effective inputs and assumptions the run
executed under, so a reviewer can audit *how* a winner was produced and compare
candidates on equal footing.

Unlike the per-window/per-candidate audit tables (0022), which link to member
runs to avoid drift, the manifest deliberately **freezes** (copies) the effective
values — that snapshot is the point. It captures what the experiment row does not:
the run economics (initial cash, benchmark, slippage, fee), the book's effective
risk/sizing knobs (``effective_execution_json``), exact universe membership +
lineage, the market-data provider + an as-of timestamp, and the engine/source
revision. Two JSON columns hold a frozen settings snapshot and a variable-length
ticker list — the same frozen-audit-payload shape ``promotion_reviews`` uses, not
generic key/value storage.

It is a **provenance and audit record, not a replay guarantee**: no input price
payloads are stored, so a later rerun may differ if the provider revised history.
``manifest_version`` is versioned so a future field addition is a new version,
never a silent redefinition.

Self-contained by convention: no application imports, literal DDL only. A new
1:1 child table (pure CREATE); the downgrade drops it.
"""

from __future__ import annotations

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE optimization_run_manifests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER NOT NULL,
            manifest_version TEXT NOT NULL,
            account_name TEXT NOT NULL,
            book_id INTEGER,
            initial_cash REAL NOT NULL,
            benchmark_ticker TEXT NOT NULL,
            slippage_bps REAL NOT NULL,
            fee_per_trade REAL NOT NULL,
            effective_execution_json TEXT NOT NULL,
            tickers_file TEXT,
            universe_history_dir TEXT,
            universe_tickers_json TEXT NOT NULL,
            universe_size INTEGER NOT NULL,
            market_data_provider TEXT NOT NULL,
            data_as_of TEXT NOT NULL,
            engine_revision TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (experiment_id) REFERENCES optimization_experiments(id) ON DELETE CASCADE,
            FOREIGN KEY (book_id) REFERENCES books(id)
        )
        """
    )
    # One manifest per experiment (1:1). The leading column also covers the
    # experiment cascade FK.
    op.execute(
        "CREATE UNIQUE INDEX idx_optimization_run_manifests_experiment ON optimization_run_manifests(experiment_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE optimization_run_manifests")
