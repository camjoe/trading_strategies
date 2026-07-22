"""Enforce orders.rotation_decision_id FK; REAL risk qty; NOT NULL accounts.updated_at.

Revision ID: 0009
Revises: 0008

Three contract tightenings from the 2026-07-17 schema overview:

- ``orders.rotation_decision_id`` gains its missing foreign key to
  ``rotation_decisions(id)`` — the one ``*_id`` column that escaped the
  "every ``*_id`` is a real, enforced FK" convention. Like the strategy FKs
  it carries no delete action: NO ACTION is checked at statement end, so the
  shared ``books`` cascade (which removes both orders and rotation_decisions
  in one statement) stays valid, and nothing deletes rotation history
  independently.
- ``risk_decisions.requested_qty``/``approved_qty`` become REAL, matching
  ``orders.qty`` so the decision log can record fractional quantities
  faithfully. The risk gate itself still decides in whole shares; this only
  stops the storage layer from truncating.
- ``accounts.updated_at`` becomes NOT NULL like every other table's;
  existing NULLs backfill from ``created_at`` (rows never updated since
  creation).

Self-contained by convention: no application imports, literal DDL only.
SQLite cannot add an FK, change a column type, or add NOT NULL in place, so
all three are explicit table rebuilds (create new -> copy -> drop -> rename
-> recreate indexes).
"""

from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

# Explicit copy lists — rebuilds must never use SELECT *.

_ACCOUNT_COLUMNS = (
    "id",
    "name",
    "account_kind",
    "base_ccy",
    "initial_cash",
    "created_at",
    "updated_at",
    "benchmark_ticker",
    "descriptive_name",
    "broker_type",
    "broker_host",
    "broker_port",
    "broker_client_id",
    "live_trading_enabled",
)

_ACCOUNTS_DDL_TEMPLATE = """
    CREATE TABLE accounts_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        account_kind TEXT NOT NULL DEFAULT 'managed',
        base_ccy TEXT NOT NULL DEFAULT 'USD',
        initial_cash REAL NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT{updated_at_constraint},
        benchmark_ticker TEXT NOT NULL DEFAULT 'SPY',
        descriptive_name TEXT NOT NULL DEFAULT '',
        broker_type TEXT NOT NULL DEFAULT 'paper',
        broker_host TEXT,
        broker_port INTEGER,
        broker_client_id INTEGER,
        live_trading_enabled INTEGER NOT NULL DEFAULT 0
    )
"""

_RISK_DECISION_COLUMNS = (
    "id",
    "account_id",
    "book_id",
    "decision_time",
    "symbol",
    "side",
    "action",
    "reason_code",
    "requested_qty",
    "approved_qty",
    "requested_notional",
    "approved_notional",
    "risk_payload_json",
    "created_at",
)

_RISK_DECISIONS_DDL_TEMPLATE = """
    CREATE TABLE risk_decisions_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        book_id INTEGER,
        decision_time TEXT NOT NULL,
        symbol TEXT,
        side TEXT CHECK (side IS NULL OR side IN ('buy', 'sell')),
        action TEXT NOT NULL CHECK (action IN ('allow', 'rescale', 'block')),
        reason_code TEXT NOT NULL,
        requested_qty {qty_type},
        approved_qty {qty_type},
        requested_notional REAL,
        approved_notional REAL,
        risk_payload_json TEXT NOT NULL DEFAULT '{{}}',
        created_at TEXT NOT NULL,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
        FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE SET NULL
    )
"""

_RISK_DECISIONS_INDEXES = (
    "CREATE INDEX idx_risk_decisions_account_time ON risk_decisions(account_id, decision_time DESC)",
    "CREATE INDEX idx_risk_decisions_book_time ON risk_decisions(book_id, decision_time DESC)",
)

_ORDER_COLUMNS = (
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
)

_ORDERS_DDL_TEMPLATE = """
    CREATE TABLE orders_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL,
        account_id INTEGER NOT NULL,
        strategy_id INTEGER,
        rotation_decision_id INTEGER,
        broker_order_id TEXT,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
        qty REAL NOT NULL,
        order_type TEXT NOT NULL DEFAULT 'market' CHECK (order_type IN ('market', 'limit')),
        time_in_force TEXT NOT NULL DEFAULT 'day' CHECK (time_in_force IN ('day', 'gtc')),
        requested_price REAL,
        status TEXT NOT NULL CHECK (
            status IN ('submitted', 'partially_filled', 'filled', 'rejected', 'cancelled')
        ),
        filled_qty REAL NOT NULL DEFAULT 0,
        avg_fill_price REAL,
        commission REAL NOT NULL DEFAULT 0,
        submitted_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
        FOREIGN KEY (strategy_id) REFERENCES strategies(id){rotation_fk}
    )
"""

_ORDERS_ROTATION_FK = """,
        FOREIGN KEY (rotation_decision_id) REFERENCES rotation_decisions(id)"""

_ORDERS_INDEXES = (
    (
        "CREATE UNIQUE INDEX idx_orders_account_broker_order_id "
        "ON orders(account_id, broker_order_id) WHERE broker_order_id IS NOT NULL"
    ),
    "CREATE INDEX idx_orders_account_status_submitted ON orders(account_id, status, submitted_at DESC)",
    "CREATE INDEX idx_orders_book_submitted ON orders(book_id, submitted_at DESC)",
)


def _check_foreign_keys() -> None:
    orphans = op.get_bind().exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if orphans:
        raise RuntimeError(f"revision 0009 rebuild left FK violations: {orphans!r}")


def _rebuild_accounts(*, updated_at_constraint: str) -> None:
    column_list = ", ".join(_ACCOUNT_COLUMNS)
    op.execute(_ACCOUNTS_DDL_TEMPLATE.format(updated_at_constraint=updated_at_constraint))
    op.execute(f"INSERT INTO accounts_new ({column_list}) SELECT {column_list} FROM accounts")
    op.execute("DROP TABLE accounts")
    op.execute("ALTER TABLE accounts_new RENAME TO accounts")


def _rebuild_risk_decisions(*, qty_type: str) -> None:
    column_list = ", ".join(_RISK_DECISION_COLUMNS)
    op.execute(_RISK_DECISIONS_DDL_TEMPLATE.format(qty_type=qty_type))
    op.execute(f"INSERT INTO risk_decisions_new ({column_list}) SELECT {column_list} FROM risk_decisions")
    op.execute("DROP TABLE risk_decisions")
    op.execute("ALTER TABLE risk_decisions_new RENAME TO risk_decisions")
    for index_sql in _RISK_DECISIONS_INDEXES:
        op.execute(index_sql)


def _rebuild_orders(*, rotation_fk: str) -> None:
    column_list = ", ".join(_ORDER_COLUMNS)
    op.execute(_ORDERS_DDL_TEMPLATE.format(rotation_fk=rotation_fk))
    op.execute(f"INSERT INTO orders_new ({column_list}) SELECT {column_list} FROM orders")
    op.execute("DROP TABLE orders")
    op.execute("ALTER TABLE orders_new RENAME TO orders")
    for index_sql in _ORDERS_INDEXES:
        op.execute(index_sql)


def upgrade() -> None:
    # Rows never updated since creation report their creation time.
    op.execute("UPDATE accounts SET updated_at = created_at WHERE updated_at IS NULL")
    _rebuild_accounts(updated_at_constraint=" NOT NULL")
    _rebuild_risk_decisions(qty_type="REAL")
    _rebuild_orders(rotation_fk=_ORDERS_ROTATION_FK)
    _check_foreign_keys()


def downgrade() -> None:
    # Restores the 0008 shapes; backfilled updated_at values are kept (they
    # are valid in the nullable shape), fractional qty values round-trip via
    # SQLite INTEGER affinity.
    _rebuild_orders(rotation_fk="")
    _rebuild_risk_decisions(qty_type="INTEGER")
    _rebuild_accounts(updated_at_constraint="")
    _check_foreign_keys()
