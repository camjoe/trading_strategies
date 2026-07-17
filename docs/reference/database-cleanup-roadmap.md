# Database Cleanup Roadmap

Type: notes
Status: Complete
Created: 2026-07-13
Last Reviewed: 2026-07-17
Purpose: Record of the 2026-07 full-schema cleanup (accounts shrink, trade-history unification,
referential integrity) and the follow-ups that remain.
Related: [Database Schema Reference](db-schema.md), [DB Migration System](db-migration-system.md)

## Outcome

The schema reached its target shape on 2026-07-17: `accounts` holds identity, custody, and broker
connection only; `books` are the execution units and own execution/option/goal settings and
required `trade_universes`; trade history is `orders`/`order_fills` (book-keyed). The live
database is upgraded through revision `0008`.

What each revision delivered (full per-item history is in this file's git history):

| Revision | Change |
|---|---|
| `0002` | `rotation_decisions` rebuilt to full CASCADE (account-deletion cascade) |
| `0003` | 17 account rotation columns dropped (`book_rotation_settings` is the home) |
| `0004` | Execution settings folded into `books` columns; `book_execution_settings` dropped |
| `0005` | Option settings folded into `books` columns; `book_option_settings` dropped |
| `0006` | `trades` table retired; account state replays fills + ledger (`orders`/`order_fills`) |
| `0007` | `promotion_reviews.strategy_id` FK added (`strategy_name` stays as display snapshot) |
| `0008` | Account goal/strategy/universe columns dropped; `book_universe_history` added; `books.trade_universes` NOT NULL |

Decisions taken along the way (all 2026-07-16): settings live as columns on `books`, not 1:1
tables (`book_rotation_settings` excepted — large, coherent, sparse); broker connection stays on
`accounts` as custody metadata; universe definitions stay file-backed with the book as the only
config home. Semantic consequences are documented in [db-schema.md](db-schema.md).

## Open follow-ups

- **Universe membership snapshots** (deferred from OD6): universe definitions are file-backed;
  `book_universe_history` records names, not membership. Promoting universes to DB entities with
  membership snapshots is deferred until universe definitions stabilize — "membership drift" is a
  known, accepted gap.
- **Retention decisions**: promotion, risk, backtest, and walk-forward history retention still
  need explicit product/operator decisions (out of scope for the schema cleanup).

## Standing practices

- Re-run the FK index audit after any table rebuild: every FK column referenced by a cascade
  delete or a routine filter should be covered by an index prefix.
- After any schema change: regenerate `docs/reference/database-diagram-viewer.html`, sync
  [db-schema.md](db-schema.md), and run `python -m scripts.checks.docs.readme_check`.
- Durable design rules: typed tables and columns, never generic EAV/category/value storage; no
  mapping tables unless genuinely many-to-many or historical; physical schema changes go through
  numbered Alembic revisions only (ADR 015), each rebuild following the `0002` pattern with a
  reversible downgrade.
