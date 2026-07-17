# ADR: Book-Keyed Execution Model

Type: adr
Status: Accepted
Created: 2026-07-09
Last Reviewed: 2026-07-17
Purpose: Record the accepted book-keyed execution primitive after sleeve retirement.
Related: [Overview](../overview.md), [ADR 014 Execution-Mode Collapse](014-execution-mode-collapse.md), [Architecture Conventions](../architecture/architecture-conventions.md), [Database Schema](../reference/db-schema.md)

## Context

The earlier sleeve virtualization design introduced a separate execution concept beside accounts.
During the rewrite and sleeve-retirement work, the system needed one persistent primitive that could
represent a bounded pool of capital inside a broker account without carrying two live execution
paths.

Alternatives considered were keeping sleeves, using a generic "trading unit" name, or using a
finance-native "book" model.

The retired sleeve design is no longer kept as a live ADR; recover it from git history if the
pre-book model needs to be reconstructed.

## Decision

Use **book** as the execution primitive. A book is a bounded pool of capital inside an account, run
to one active strategy assignment and book-keyed rotation/accounting flow.

Account-level execution remains the compatibility case around a default book. New runtime,
rotation, risk, and reporting work should be book-keyed unless it is explicitly about broker account
identity.

## Consequences

- Sleeve vocabulary and sleeve-specific execution paths are retired.
- `book_id` is the preferred persistent key for strategy assignment, rotation decisions, book
  settings, and book accounting.
- Broker accounts still own custody, broker routing, cash/position truth, and the
  `live_trading_enabled` safety gate.
- Any future execution-mode cleanup should collapse remaining account-mode compatibility onto the
  default-book model rather than reintroducing a separate execution primitive. Done — see
  [ADR 014](014-execution-mode-collapse.md).
