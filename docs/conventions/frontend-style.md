# Frontend Style Guide

Type: convention
Status: Active
Created: 2026-06-19
Last Reviewed: 2026-07-13
Purpose: TypeScript / Vite frontend style for `apps/paper_trading_web/frontend/`.
Related: [General Style](general-style.md), [Python Style](python-style.md), [UI Map](../maps/ui-map.md)

Style for the operator UI (`apps/paper_trading_web/frontend/`, vanilla TypeScript + Vite).
Python style is in [`python-style.md`](python-style.md); the cross-cutting approach and
documentation style are in [`general-style.md`](general-style.md).

## Structure

1. Keep the frontend framework-free unless a fresh architecture decision changes that.
2. Treat `apps/paper_trading_web/frontend/src/views/*.html` as page entry surfaces. Wire behavior from feature modules rather than
   embedding substantial logic in HTML.
3. Put user-facing workflow logic in `apps/paper_trading_web/frontend/src/features/<area>/`.
4. Put reusable DOM, HTTP, date/number formatting, and other cross-feature helpers in
   `apps/paper_trading_web/frontend/src/lib/`.
5. Put API response and shared frontend types in `apps/paper_trading_web/frontend/src/types/`.
6. Keep generated reference assets in `apps/paper_trading_web/frontend/src/assets/`; update their source docs/scripts, then regenerate
   rather than hand-editing generated JSON.

## TypeScript

1. Keep modules focused and strongly typed.
2. Favor composition over large monolithic feature modules.
3. Prefer explicit API response types over ad-hoc object shapes.
4. Keep DOM lookups close to the feature wiring that owns the view.
5. Avoid broad rewrites when touching legacy JavaScript-style code; apply the balanced style rule from
   [`general-style.md`](general-style.md).

## CSS

1. Preserve existing design tokens and base styles.
2. Put shared tokens/base rules in `apps/paper_trading_web/frontend/src/styles/`; keep feature-specific CSS scoped to the feature area
   or the existing local stylesheet pattern.
3. Define or adjust CSS variables before spreading repeated literal colors, spacing, or sizing across
   components.

## Tooling

Run frontend commands from `apps/paper_trading_web/frontend/`:

```powershell
npm run lint
npm run typecheck
npm run test
```
