# ADR: Sleeve Virtualization Architecture for IBKR Paper Autonomy

Type: adr
Status: Superseded
Created: 2026-05-03
Last Reviewed: 2026-06-16
Purpose: Record the proposed design for sleeve virtualization, allowing one broker account to host multiple independent strategy sleeves.
Related: [Broker Integration](../reference/broker-integration.md)

> **Superseded (2026-07-09, sleeve retirement).** The sleeve concept this ADR introduced was
> realized and then generalized into first-class **books** on the clean schema (P3/P4): one
> account hosts many books; `books` + `book_strategy_assignments` replaced `strategy_sleeves` +
> `sleeve_strategy_assignments`, and the sleeve tables/repositories/vocabulary were removed
> (git history: the `features/sleeve-retirement` branch, phases SR-1…SR-7). The architectural
> intent — multiple independent strategy units inside one broker account, attributed and risk-gated
> per unit — lives on unchanged in the book model.

## Context

The current runtime architecture executes and attributes activity at account scope:

- orders and fills are persisted against `accounts`
- performance evidence is strategy-aware but fundamentally account-backed
- rotation is account-level strategy selection

The IBKR paper autonomy target requires one broker account to host multiple internal strategy sleeves with independent accounting, while preserving broker-level constraints and reconciliation safety.

## Decision

Adopt an explicit sleeve domain model linked to a broker account, with sleeve accounting and decisioning owned in service/domain layers above broker adapters.

### Core decisions

1. Keep `accounts` semantics unchanged as broker/custody entities.
2. Add sleeve-specific tables rather than overloading account tables.
3. Preserve broker adapters as sleeve-agnostic execution transports.
4. Treat sleeve attribution as internal ledgering that reconciles to broker/account truth.
5. Implement sleeve mode behind explicit rollout toggles while account mode remains compatible.

## Layer Ownership

1. `interfaces`
- Runtime job orchestration for sleeve DAG steps.

2. `services`
- Sleeve orchestration, reconciliation, risk gating, scoring, and rotation workflows.

3. `domain`
- Pure sleeve accounting/risk/selection policy math.

4. `repositories`
- Sleeve SQL persistence and retrieval.

5. `database`
- Table/index DDL and additive migrations.

6. `brokers`
- No sleeve logic; continue to place/cancel/poll broker orders.

## Reuse and Consolidation Direction

1. Reuse existing scheduler and runtime entrypoints where possible.
2. Extend existing migration/bootstrap mechanisms; do not create a second migration framework.
3. Reuse account-level broker submission/reconciliation flow as base, then lift attribution to sleeve-aware persistence.
4. Remove or deprecate duplicate paths only after sleeve-path parity and regression checks pass.

## Consequences

Benefits:

- Clear separation between broker account truth and internal strategy sleeves.
- Strong auditability of sleeve-level decisions and PnL attribution.
- Safer transition path using additive schema and compatibility mode.

Trade-offs:

- More tables and cross-entity reconciliation logic.
- Higher integration-test burden across runtime, accounting, and risk paths.

## Non-Goals

1. Live broker enablement changes.
2. Auto-generated strategy authoring.
3. Fully autonomous unguided parameter search.

## Acceptance Signals for This ADR

1. Sleeve tables and repository contracts are additive and idempotent in DB init/migration flow.
2. Runtime can execute in account mode and sleeve mode without inversion of dependency boundaries.
3. Sleeve equity reconciliation to account-level truth is explicit and reported.
