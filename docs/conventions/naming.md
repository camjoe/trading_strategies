## Adr file example

docs/adr
- ADR-001-service-layer.md
- ADR-002-soft-deletes.md
- ADR-003-postgresql.md


## adr example
'''
# ADR-002: Soft Deletes

Status: Accepted

## Context

Court records must be recoverable.

## Decision

Records will use an IsDeleted flag instead of physical deletion.

## Consequences

Pros:
- Recoverability
- Auditability

Cons:
- More query complexity
'''