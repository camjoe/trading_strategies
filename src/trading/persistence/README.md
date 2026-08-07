# Persistence

## Purpose

Mechanics shared by everything that reads and writes the database. No SQL of its own, no tables, no
domain concepts — just what every data-access module needs and would otherwise re-implement.

The split from `infrastructure/database/` is **getting** a connection versus **using** one. That
package owns backend selection, path/config, schema version, and migrations. This one owns what
trading code does with a connection once it holds it.

## Why it is its own package

It sits *below* the repository layer, which is what lets three groups share it without borrowing
from each other:

- `trading/repositories/` and `trading/backtesting/repositories/` — two repository packages in
  separate bounded contexts. Before this package existed, backtesting imported
  `trading.repositories.unit_of_work`, reaching into another context for a helper.
- `trading/services/**` — a dozen service modules open transaction scopes. They cannot import
  `infrastructure.database.*`; `scripts/checks/repo/layer_check.py` forbids it, so this
  machinery could not live there.

The package imports nothing from `trading/` or `infrastructure/`, enforced by its own layer rule.

## Modules

| Module | Responsibility |
|---|---|
| `unit_of_work.py` | Re-entrant transaction scope + the `commit_unit_of_work` helper every repository write calls |
| `json_columns.py` | The one spelling for JSON stored in a column — `dumps_json_column` / `read_json_object` |
| `change_events.py` | The old/new field diff behind the settings change-event trail |

### JSON columns

`dumps_json_column` sorts keys and emits no insignificant whitespace, so identical data
written by different code paths lands as identical text. That is what makes a column diffable
and what makes a hash over its contents stable — `params_fingerprint` in the walk-forward
optimizer is a SHA-256 over exactly this encoding.

Every JSON column write in `src/trading/` routes through it, with one deliberate exception:
`domain/rotation/schedule.py:dump_rotation_schedule`. Its value is a *list*, so `sort_keys` is
a no-op and its output is already byte-identical to the codec's — converting it would buy
nothing and would make `domain/` import a persistence module, which no domain code does today.

Uses that are **not** column writes stay on plain `json.dumps`: the market-data file cache,
runtime job artifacts and log lines, and notification bodies. Those are read by humans or by
other systems, and several want `indent=2`.

## Usage

```python
from trading.persistence.unit_of_work import unit_of_work

with unit_of_work(conn):
    order_id = OrderRepository(conn).insert(...)   # no commit yet
    PositionRepository(conn).upsert(...)           # no commit yet
# one COMMIT here on clean exit; a raise anywhere above rolls all of it back
```

Keep broker/network calls **outside** the scope — never hold a write transaction open across I/O.

## Related

- [Database Transactions](../../../docs/reference/database-transactions.md) — the unit-of-work pattern in full
- [Repositories](../repositories/README.md) — the table modules above this layer
- [Architecture Conventions](../../../docs/architecture/architecture-conventions.md) — layer boundaries
