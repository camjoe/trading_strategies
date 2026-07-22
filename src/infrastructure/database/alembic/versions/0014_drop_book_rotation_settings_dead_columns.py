"""Drop the eleven unused book rotation settings columns.

Revision ID: 0014
Revises: 0013

The removed cadence, regime-mapping, and overlay columns have no application
reader or writer. Rotation scheduling uses the enabled gate, schedule, and
lookback; champion/challenger policy uses the retained evidence, cooldown, and
score-weight columns.

SQLite requires an explicit copy-and-rebuild because three removed regime
columns participate in foreign keys. The upgrade refuses to discard any
non-NULL legacy value, preserves the active settings and book cascade, and
checks foreign-key integrity after rebuilding. The downgrade restores the
retired nullable columns empty; only a pre-upgrade backup could recover values
if a database had them, although the upgrade guard prevents that case.
"""

from __future__ import annotations

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_KEPT_COLUMNS = (
    "book_id",
    "rotation_enabled",
    "rotation_lookback_days",
    "rotation_schedule",
    "min_trades_in_window",
    "outperformance_threshold_bps",
    "cooldown_days",
    "risk_adjusted_return_weight",
    "stability_weight",
    "drawdown_penalty_weight",
    "cost_penalty_weight",
    "regime_fit_weight",
    "created_at",
    "updated_at",
)

_DROPPED_COLUMNS = (
    "rotation_mode",
    "rotation_optimality_mode",
    "rotation_interval_days",
    "rotation_interval_minutes",
    "regime_strategy_risk_on_id",
    "regime_strategy_neutral_id",
    "regime_strategy_risk_off_id",
    "overlay_mode",
    "overlay_min_tickers",
    "overlay_confidence_threshold",
    "overlay_watchlist",
)

_DDL_WITHOUT_DEAD_COLUMNS = """
    CREATE TABLE book_rotation_settings_new (
        book_id INTEGER PRIMARY KEY,
        rotation_enabled INTEGER NOT NULL DEFAULT 0 CHECK (rotation_enabled IN (0, 1)),
        rotation_lookback_days INTEGER,
        rotation_schedule TEXT,
        min_trades_in_window INTEGER,
        outperformance_threshold_bps REAL,
        cooldown_days INTEGER,
        risk_adjusted_return_weight REAL,
        stability_weight REAL,
        drawdown_penalty_weight REAL,
        cost_penalty_weight REAL,
        regime_fit_weight REAL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
    )
"""

_DDL_WITH_DEAD_COLUMNS = """
    CREATE TABLE book_rotation_settings_new (
        book_id INTEGER PRIMARY KEY,
        rotation_enabled INTEGER NOT NULL DEFAULT 0 CHECK (rotation_enabled IN (0, 1)),
        rotation_mode TEXT,
        rotation_optimality_mode TEXT,
        rotation_interval_days INTEGER,
        rotation_interval_minutes INTEGER,
        rotation_lookback_days INTEGER,
        rotation_schedule TEXT,
        min_trades_in_window INTEGER,
        outperformance_threshold_bps REAL,
        cooldown_days INTEGER,
        risk_adjusted_return_weight REAL,
        stability_weight REAL,
        drawdown_penalty_weight REAL,
        cost_penalty_weight REAL,
        regime_fit_weight REAL,
        regime_strategy_risk_on_id INTEGER,
        regime_strategy_neutral_id INTEGER,
        regime_strategy_risk_off_id INTEGER,
        overlay_mode TEXT,
        overlay_min_tickers INTEGER,
        overlay_confidence_threshold REAL,
        overlay_watchlist TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
        FOREIGN KEY (regime_strategy_risk_on_id) REFERENCES strategies(id),
        FOREIGN KEY (regime_strategy_neutral_id) REFERENCES strategies(id),
        FOREIGN KEY (regime_strategy_risk_off_id) REFERENCES strategies(id)
    )
"""


def _check_foreign_keys() -> None:
    orphans = op.get_bind().exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if orphans:
        raise RuntimeError(f"revision 0014 rebuild left FK violations: {orphans!r}")


def _rebuild(*, ddl: str) -> None:
    column_list = ", ".join(_KEPT_COLUMNS)
    op.execute(ddl)
    op.execute(
        f"INSERT INTO book_rotation_settings_new ({column_list}) SELECT {column_list} FROM book_rotation_settings"
    )
    op.execute("DROP TABLE book_rotation_settings")
    op.execute("ALTER TABLE book_rotation_settings_new RENAME TO book_rotation_settings")
    _check_foreign_keys()


def upgrade() -> None:
    populated_predicate = " OR ".join(f"{column} IS NOT NULL" for column in _DROPPED_COLUMNS)
    populated_row = (
        op.get_bind()
        .exec_driver_sql(f"SELECT book_id FROM book_rotation_settings WHERE {populated_predicate} LIMIT 1")
        .fetchone()
    )
    if populated_row is not None:
        raise RuntimeError(
            "revision 0014 refuses to discard populated book_rotation_settings columns; "
            f"book_id={populated_row[0]!r} has legacy configuration"
        )
    _rebuild(ddl=_DDL_WITHOUT_DEAD_COLUMNS)


def downgrade() -> None:
    # Restores the 0013 shape. The retired nullable columns return empty; the
    # upgrade guard ensures no values were discarded during a normal upgrade.
    _rebuild(ddl=_DDL_WITH_DEAD_COLUMNS)
