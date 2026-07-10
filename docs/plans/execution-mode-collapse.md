# Execution Mode Collapse Plan

Type: notes
Status: Active (deferred)
Created: 2026-07-09
Last Reviewed: 2026-07-09
Purpose: Capture the deferred refactor to collapse account/book runtime modes after sleeve retirement.
Related: [Plans Index](README.md), [Overview](../overview.md), [ADR 010](../adr/010-book-keyed-execution-model.md)

## Purpose

This refactor would simplify runtime mode handling now that sleeves are retired and books are the
execution primitive.

## Current State

- Books are the persistent execution primitive.
- The runtime still carries account-mode compatibility paths and naming in some places.
- Sleeve retirement removed the old sleeve paradigm, but did not change account-mode strategy and
  state resolution semantics.

## Intended Shape

- Runtime trades every assigned book.
- Account mode becomes a default-book case rather than a separate execution concept.
- Strategy resolution, rotation state, and accounting use book-keyed flow consistently.

## Decisions To Make

- Exact compatibility behavior for existing account-mode profiles.
- Whether profile fields should be rewritten, shimmed, or accepted as legacy input.
- Which UI/API labels should change, if any, after the runtime contract is simplified.

## Trigger

Revisit when runtime mode handling is next touched. The refactor should stay separate from unrelated
feature work.
