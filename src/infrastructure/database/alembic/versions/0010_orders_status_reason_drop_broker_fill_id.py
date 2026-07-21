"""Add orders.status_reason; drop duplicative order_fills.broker_fill_id.

Revision ID: 0010
Revises: 0009

Two findings from the 2026-07-17 execution/accounting-quartet review:

- ``orders.status_reason`` (nullable TEXT) gives broker rejection/cancellation
  reasons a home. Today the status column is overwritten in place with no
  "why"; gate blocks are captured in ``risk_decisions`` but broker-side
  reasons evaporated. The persistence path is wired end to end
  (``BrokerOrder.status_reason`` -> ``OrderRepository.insert`` /
  ``update_status``); populating it from the IB adapters is a bounded
  follow-up under the Live Trading Safety Guard.
- ``order_fills.broker_fill_id`` is dropped. Every write site set it to the
  parent order's ``broker_order_id`` (a copy of ``orders.broker_order_id``
  under a misleading name), never a per-fill broker id. ``exec_id`` already
  carries per-execution identity and dedup (``UNIQUE(order_id, exec_id)``).

Self-contained by convention: no application imports, literal DDL only.
``orders.status_reason`` is a plain additive nullable column (ADD COLUMN).
Dropping a column is an explicit table rebuild (SQLite cannot drop a column
in place here without reflection guessing at the unnamed UNIQUE constraint),
so ``order_fills`` is rebuilt in both directions.
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

# Columns preserved across the order_fills rebuild (both directions). broker_fill_id
# is never copied: dropped on upgrade, and restored as NULL on downgrade.
_ORDER_FILLS_KEPT_COLUMNS = (
    "id",
    "order_id",
    "exec_id",
    "filled_qty",
    "fill_price",
    "commission",
    "fill_time",
)

_ORDER_FILLS_DDL_TEMPLATE = """
    CREATE TABLE order_fills_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,{broker_fill_id_column}
        exec_id TEXT,
        filled_qty REAL NOT NULL,
        fill_price REAL NOT NULL,
        commission REAL NOT NULL DEFAULT 0,
        fill_time TEXT NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
        UNIQUE (order_id, exec_id)
    )
"""

_BROKER_FILL_ID_COLUMN = "\n        broker_fill_id TEXT,"

_ORDER_FILLS_INDEX = "CREATE INDEX idx_order_fills_order_id ON order_fills(order_id)"


def _check_foreign_keys() -> None:
    orphans = op.get_bind().exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if orphans:
        raise RuntimeError(f"revision 0010 rebuild left FK violations: {orphans!r}")


def _rebuild_order_fills(*, with_broker_fill_id: bool) -> None:
    column_list = ", ".join(_ORDER_FILLS_KEPT_COLUMNS)
    broker_fill_id_column = _BROKER_FILL_ID_COLUMN if with_broker_fill_id else ""
    op.execute(_ORDER_FILLS_DDL_TEMPLATE.format(broker_fill_id_column=broker_fill_id_column))
    op.execute(f"INSERT INTO order_fills_new ({column_list}) SELECT {column_list} FROM order_fills")
    op.execute("DROP TABLE order_fills")
    op.execute("ALTER TABLE order_fills_new RENAME TO order_fills")
    op.execute(_ORDER_FILLS_INDEX)


def upgrade() -> None:
    op.execute("ALTER TABLE orders ADD COLUMN status_reason TEXT")
    _rebuild_order_fills(with_broker_fill_id=False)
    _check_foreign_keys()


def downgrade() -> None:
    _rebuild_order_fills(with_broker_fill_id=True)
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("status_reason")
    _check_foreign_keys()
