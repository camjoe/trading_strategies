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

- `trading/repositories/` and `backtesting/repositories/` — two repository packages in
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
| `change_events.py` | The old/new field diff behind the settings change-event trail |

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
