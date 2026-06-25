# Frontend Style Guide

Type: convention
Status: Active
Created: 2026-06-19
Last Reviewed: 2026-06-19
Purpose: TypeScript / Vite frontend style for `apps/paper_trading_web/frontend/` — kept separate so it can grow as the UI does.
Related: [General Style](general-style.md), [Python Style](python-style.md), [UI Map](../maps/ui-map.md)

Style for the operator UI (`apps/paper_trading_web/frontend/`, vanilla TypeScript + Vite). Python style is in [`python-style.md`](python-style.md); the cross-cutting approach and documentation style are in [`general-style.md`](general-style.md).

## TypeScript and Frontend

1. Keep components focused and strongly typed.
2. Favor composition over large monolithic components.
3. Preserve existing design system patterns when present.
4. If no design system exists and restyling is requested, define theme tokens (CSS variables) before per-component styles.

> This guide is intentionally small for now. Expand it as frontend conventions solidify — e.g. module/feature structure, state handling, formatting/lint config, and component testing patterns.
