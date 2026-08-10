"""Add orders.client_order_id and the 'pending' status.

Revision ID: 0031
Revises: 0030

An order was written to the database only after the broker answered, so a crash
between the send and that write left the broker holding an order no row
recorded. Reconciliation could not find it either: it matches on
``broker_order_id``, which does not exist until the broker replies, so nothing
identified the order on both sides.

``client_order_id`` is that identifier — generated before the send, carried to
the broker (Web API ``cOID``, socket ``orderRef``), and echoed back. The row is
now written *before* the send with status ``pending``, which is why the status
CHECK gains a sixth value. ``pending`` means "sent, no answer yet" and is
distinct from a broker reporting PendingSubmit, which is an acknowledged order
and still maps to ``submitted``.

Self-contained by convention: no application imports, literal DDL only.

**The rebuild carries order_fills.** SQLite cannot alter a CHECK constraint in
place, and migrations run with ``PRAGMA foreign_keys = ON``, so dropping
``orders`` cascades through ``order_fills.order_id`` and deletes every fill —
silently, with ``PRAGMA foreign_key_check`` reporting nothing afterwards. Since
revision 0006 retired the ``trades`` table those rows are the only execution
history there is, so they are copied to an unconstrained carry table first and
restored after the rename. The row counts are asserted in both directions.
"""

from __future__ import annotations

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

# Column order matches the rebuilt table: client_order_id sits beside
# broker_order_id because they are the same order's two identities.
_ORDERS_CARRIED_COLUMNS = (
    "id",
    "book_id",
    "account_id",
    "strategy_id",
    "rotation_decision_id",
    "broker_order_id",
    "symbol",
    "side",
    "qty",
    "order_type",
    "time_in_force",
    "requested_price",
    "status",
    "filled_qty",
    "avg_fill_price",
    "commission",
    "submitted_at",
    "updated_at",
    "status_reason",
    "realized_pnl_delta",
)

_ORDER_FILLS_COLUMNS = (
    "id",
    "order_id",
    "exec_id",
    "filled_qty",
    "fill_price",
    "commission",
    "fill_time",
)

_ORDERS_DDL_TEMPLATE = """
    CREATE TABLE orders_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL,
        account_id INTEGER NOT NULL,
        strategy_id INTEGER,
        rotation_decision_id INTEGER,
        broker_order_id TEXT,{client_order_id_column}
        symbol TEXT NOT NULL,
        side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
        qty REAL NOT NULL,
        order_type TEXT NOT NULL DEFAULT 'market' CHECK (order_type IN ('market', 'limit')),
        time_in_force TEXT NOT NULL DEFAULT 'day' CHECK (time_in_force IN ('day', 'gtc')),
        requested_price REAL,
        status TEXT NOT NULL CHECK (
            status IN ({status_values})
        ),
        filled_qty REAL NOT NULL DEFAULT 0,
        avg_fill_price REAL,
        commission REAL NOT NULL DEFAULT 0,
        submitted_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        status_reason TEXT,
        realized_pnl_delta REAL,
        FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
        FOREIGN KEY (strategy_id) REFERENCES strategies(id),
        FOREIGN KEY (rotation_decision_id) REFERENCES rotation_decisions(id)
    )
"""

_CLIENT_ORDER_ID_COLUMN = "\n        client_order_id TEXT,"

_STATUS_VALUES_WITH_PENDING = "'pending', 'submitted', 'partially_filled', 'filled', 'rejected', 'cancelled'"
_STATUS_VALUES_ORIGINAL = "'submitted', 'partially_filled', 'filled', 'rejected', 'cancelled'"

_ORDERS_INDEXES = (
    "CREATE INDEX idx_orders_book_submitted ON orders(book_id, submitted_at DESC)",
    "CREATE INDEX idx_orders_account_status_submitted ON orders(account_id, status, submitted_at DESC)",
    "CREATE UNIQUE INDEX idx_orders_account_broker_order_id "
    "ON orders(account_id, broker_order_id) WHERE broker_order_id IS NOT NULL",
)

# Partial-unique, mirroring the broker_order_id index: an account never reuses a
# client order id, and rows predating this revision carry NULL.
_CLIENT_ORDER_ID_INDEX = (
    "CREATE UNIQUE INDEX idx_orders_account_client_order_id "
    "ON orders(account_id, client_order_id) WHERE client_order_id IS NOT NULL"
)


def _row_count(table: str) -> int:
    return int(op.get_bind().exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar() or 0)


def _rebuild_orders(*, with_client_order_id: bool, status_values: str) -> None:
    """Rebuild orders, preserving order_fills across the cascading drop."""
    fills_before = _row_count("order_fills")
    fill_columns = ", ".join(_ORDER_FILLS_COLUMNS)
    order_columns = ", ".join(_ORDERS_CARRIED_COLUMNS)

    # Unconstrained by design: the carry table must not reference orders, or the
    # drop below would cascade into it too.
    op.execute(f"CREATE TABLE order_fills_carry AS SELECT {fill_columns} FROM order_fills")

    client_order_id_column = _CLIENT_ORDER_ID_COLUMN if with_client_order_id else ""
    op.execute(_ORDERS_DDL_TEMPLATE.format(client_order_id_column=client_order_id_column, status_values=status_values))
    op.execute(f"INSERT INTO orders_new ({order_columns}) SELECT {order_columns} FROM orders")
    op.execute("DROP TABLE orders")
    op.execute("ALTER TABLE orders_new RENAME TO orders")
    for statement in _ORDERS_INDEXES:
        op.execute(statement)
    if with_client_order_id:
        op.execute(_CLIENT_ORDER_ID_INDEX)

    op.execute(f"INSERT INTO order_fills ({fill_columns}) SELECT {fill_columns} FROM order_fills_carry")
    op.execute("DROP TABLE order_fills_carry")

    fills_after = _row_count("order_fills")
    if fills_after != fills_before:
        raise RuntimeError(f"revision 0031 lost order_fills rows: {fills_before} before, {fills_after} after.")
    orphans = op.get_bind().exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if orphans:
        raise RuntimeError(f"revision 0031 rebuild left FK violations: {orphans!r}")


def upgrade() -> None:
    _rebuild_orders(with_client_order_id=True, status_values=_STATUS_VALUES_WITH_PENDING)


def downgrade() -> None:
    # A pending order was sent and never confirmed. The pre-0031 vocabulary has no
    # word for that, and 'submitted' is the closest — it is what the row would have
    # said had it been written after the send, as it was before this revision.
    op.execute("UPDATE orders SET status = 'submitted' WHERE status = 'pending'")
    _rebuild_orders(with_client_order_id=False, status_values=_STATUS_VALUES_ORIGINAL)
