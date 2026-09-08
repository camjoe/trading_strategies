"""Store resolved tickers on books instead of universe names.

Revision ID: 0029
Revises: 0028

``books.trade_universes`` held universe *names* (``["default"]``) that the
trading path resolved against ``src/infrastructure/config/trade_universes/*.txt``
on every run. Two consequences made that the wrong home for the value:

- ``book_universe_history`` versioned the names, not their contents, so editing
  a universe file retroactively changed what every past run and backtest had
  been trading. Point-in-time membership was unrecoverable.
- Resolution happened at trade time, so an unresolvable name surfaced as a
  ``FileNotFoundError`` that aborted an account run rather than the config edit
  that introduced it.

Names become a write-time shorthand: callers still pass universe names, the
service resolves them, and the book stores the resulting ticker list. The
column is renamed to ``trade_symbols`` so the schema states what it holds.
``book_universe_history`` follows, and now records real membership per change.

Self-contained by convention: the name-to-ticker mapping below is a literal
snapshot of the universe files at this revision, not an import. A data
migration must reproduce the same result whatever those files later become.

``trade_universes`` participates in no CHECK constraint and no index, so
``RENAME COLUMN`` applies directly — no table rebuild.
"""

from __future__ import annotations

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

# Literal snapshot of src/infrastructure/config/trade_universes/*.txt at this
# revision. Ticker order is file order, which is the order the resolver produced.
_DEFAULT_SYMBOLS = '["AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","JPM","JNJ","UNH","XOM","WMT"]'
_GROWTH_SYMBOLS = (
    '["CRWD","SNOW","DDOG","NET","HUBS","NVDA","AMD","AVGO","AMZN","TSLA","SHOP","ISRG","VEEV","DXCM","SQ","ADYEY"]'
)

# Only single-name values existed when this revision was authored; a multi-name
# value would have been a union, which no row used.
_NAME_TO_SYMBOLS = {
    '["default"]': _DEFAULT_SYMBOLS,
    '["growth"]': _GROWTH_SYMBOLS,
}

_TABLES = ("books", "book_universe_history")


_KNOWN_SYMBOL_VALUES = f"('{_DEFAULT_SYMBOLS}', '{_GROWTH_SYMBOLS}')"
_KNOWN_NAME_VALUES = "('[\"default\"]', '[\"growth\"]')"


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} RENAME COLUMN trade_universes TO trade_symbols")
        for names, symbols in _NAME_TO_SYMBOLS.items():
            op.execute(f"UPDATE {table} SET trade_symbols = '{symbols}' WHERE trade_symbols = '{names}'")
        # A name this revision does not know (a universe file deleted before it,
        # say) cannot be resolved without reading application config. Leaving it
        # would store a name in a ticker column, where it matches no symbol and
        # the book silently trades nothing. Collapse to the default instead.
        op.execute(
            f"UPDATE {table} SET trade_symbols = '{_DEFAULT_SYMBOLS}' WHERE trade_symbols NOT IN {_KNOWN_SYMBOL_VALUES}"
        )


def downgrade() -> None:
    # Shape and the two snapshot universes only. A ticker list matching neither
    # cannot be expressed as a name, so it collapses to ["default"]; restore
    # from the pre-upgrade backup to recover real values.
    for table in _TABLES:
        for names, symbols in _NAME_TO_SYMBOLS.items():
            op.execute(f"UPDATE {table} SET trade_symbols = '{names}' WHERE trade_symbols = '{symbols}'")
        op.execute(
            f"UPDATE {table} SET trade_symbols = '[\"default\"]' WHERE trade_symbols NOT IN {_KNOWN_NAME_VALUES}"
        )
        op.execute(f"ALTER TABLE {table} RENAME COLUMN trade_symbols TO trade_universes")
