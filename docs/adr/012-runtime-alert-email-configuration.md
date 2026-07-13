# ADR: Runtime Alert Email Configuration

Type: adr
Status: Accepted
Created: 2026-07-09
Last Reviewed: 2026-07-09
Purpose: Record why runtime email alerts are configured through environment variables instead of database settings.
Related: [Runtime Operations Runbook](../runbooks/runtime-operations.md), [Runtime Jobs](../reference/runtime-jobs.md)

## Context

Runtime alerts already supported webhooks. Adding email required deciding whether SMTP host,
credentials, and recipients should live in the database, in operational settings, or in deployment
environment variables.

## Decision

Configure SMTP email alerts entirely through `TRADING_RUNTIME_ALERT_SMTP_*` environment variables.
Email is opt-in and best-effort, fanned out beside webhook notifications by the runtime notification
path. Authentication is optional so unauthenticated relays can be used, and secrets stay out of
source and database rows.

## Consequences

- Recipient changes are deployment configuration changes, not runtime database edits.
- The runtime operations runbook is the operator source of truth for SMTP variables.
- Per-transport event-class filtering is deferred until there is actual demand.
