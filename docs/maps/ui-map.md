# UI Map — `paper_trading_ui/`

Type: map
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-06-16
Purpose: Structure of the operator UI — FastAPI backend routes/schemas/services and TypeScript/Vite frontend layout.
Related: [Navigation Guide](../architecture/nav-guide.md), [UI Screenshot Notes](../reference/screenshot-ui.md)

Structure of the operator UI: a FastAPI backend and a TypeScript/Vite frontend. Both live under `paper_trading_ui/`.

---

## Backend (`paper_trading_ui/backend/`)

### Entry Points

| File | Responsibility |
|---|---|
| `main.py` | FastAPI app entry point; registers all routers |
| `config.py` | Backend config (env vars, DB path, CORS, export paths) |
| `account_options.py` | Account option helper used by multiple routes |

### Routes (`routes/`)

FastAPI routers. One file per logical domain. Routes call backend services; they do not call `trading/` directly.

| Module | Endpoints |
|---|---|
| `accounts.py` | Account listing, detail views, snapshot history |
| `actions.py` | Action-triggering endpoints (trigger trades, rotations) |
| `admin.py` | Admin operations (deletions, job trigger, artifact listing) |
| `analysis.py` | Portfolio analysis data |
| `backtests.py` | Backtest run submission and result retrieval |
| `features.py` | Feature/signal data for alternative strategies |
| `health.py` | Health check (`GET /health`) |
| `ibkr_paper_monitor.py` | IBKR paper monitor status and artifacts |
| `logs.py` | Log file access |

### Schemas (`schemas/`)

Pydantic request/response models. These define the API contract with the frontend.

| Module | Contract shapes for |
|---|---|
| `accounts.py` | Account listing, detail, snapshot responses |
| `admin.py` | Admin request/response shapes |
| `backtests.py` | Backtest run request and result shapes |
| `features.py` | Feature/signal response shapes |

### Services (`services/`)

Backend service layer — bridges routes to `trading/` package calls.

| Module | Responsibility |
|---|---|
| `db.py` | DB connection/session management for the UI backend |
| `accounts/` | Account data assembly (summaries, snapshots, detail) |
| `admin.py` | Admin operation service |
| `backtests.py` | Backtesting service (delegates to `trading/backtesting/`) |
| `exports.py` | Data export assembly |
| `features/` | Feature/signal data service |
| `ibkr_paper_monitor.py` | IBKR monitor artifact assembly |
| `operations/` | Runtime operation services (job triggers, etc.) |
| `promotion.py` | Promotion data service |

### Account Contract (`account_contract/`)

Explicit output-shape contract for account data returned to the frontend. Isolates internal model shape from frontend API shape.

| Module | Responsibility |
|---|---|
| `builders.py` | Assembles account response contract from internal models |
| `mappings.py` | Field mappings between internal models and contract |
| `models.py` | Contract models — the output shapes the frontend consumes |

---

## Frontend (`paper_trading_ui/frontend/src/`)

Vanilla TypeScript + Vite. No framework. Views are HTML files; features are TypeScript modules that wire up components to views.

### Entry Point

| File | Responsibility |
|---|---|
| `main.ts` | App entry point; view routing and feature bootstrap |

### Features (`features/`)

Top-level feature modules. Each feature coordinates a view: loads data, renders components, handles user interactions.

| Feature | Description |
|---|---|
| `accounts/` | Account browser, controller, detail view, types |
| `admin/` | Admin panel: accounts, artifacts, operations, promotions, sections, UI helpers |
| `backtesting/` | Backtest run submission, result display, constants, payloads, types |
| `alt-strategies.ts` | Alternative strategies feature |
| `compare.ts` | Account comparison feature |
| `docs/` | In-app documentation viewer: accordion, menu, helpers, constants |
| `logs.ts` | Log viewer feature |

### Components (`components/`)

Reusable UI rendering modules. Called by features.

| Module | Description |
|---|---|
| `accounts.ts` | Account list rendering |
| `account-detail/` | Account detail sections: overview, snapshots, ledger, config, analysis, header |
| `admin-ops.ts` | Admin operation buttons and status |
| `alt-strategies.ts` | Alternative strategies component |
| `backtesting.ts` | Backtesting results component |
| `detail.ts` | Generic detail panel component |
| `ibkr-paper-monitor.ts` | IBKR paper monitor status component |

### Library (`lib/`)

Shared utilities. No feature logic.

| Module | Description |
|---|---|
| `http.ts` | API client (fetch wrapper, error handling) |
| `format.ts` | Number/date/currency formatters |
| `parse.ts` | Response parsing helpers |
| `dom.ts` | DOM manipulation utilities |
| `timing.ts` | Debounce, polling, timing helpers |
| `logs.ts` | Log parsing and display utilities |
| `form-parse.ts` | Form input parsing helpers |
| `account-config-options.ts` | Account config option helpers |
| `docs-renderer/` | In-app docs renderer (api, finance, software, shared, types) |

### Types (`types/`)

TypeScript type definitions for API response shapes. One file per backend domain.

| File | Types for |
|---|---|
| `accounts.ts` | Account listing, detail, snapshot responses |
| `admin.ts` | Admin response shapes |
| `backtesting.ts` | Backtest run and result shapes |
| `compare.ts` | Account comparison shapes |
| `ibkr-paper-monitor.ts` | IBKR monitor response shapes |
| `signals.ts` | Feature/signal response shapes |

### Views (`views/`)

HTML view templates. One file per page/section. JavaScript features are bootstrapped against these.

| View | Page |
|---|---|
| `accounts.html` | Account browser page |
| `admin.html` | Admin panel root |
| `admin/accounts.html` | Admin → accounts section |
| `admin/artifacts.html` | Admin → artifacts section |
| `admin/jobs.html` | Admin → jobs section |
| `admin/overview.html` | Admin → overview section |
| `admin/promotions.html` | Admin → promotions section |
| `alt-strategies.html` | Alternative strategies page |
| `backtesting.html` | Backtesting page |
| `compare.html` | Account comparison page |
| `ibkr-paper-monitor.html` | IBKR paper monitor page |
| `trades.html` | Trades view |
| `app-layout.html` | Shared app layout shell |
| `nav.html` | Navigation component |

### Styles (`styles/`)

Per-feature CSS files and design tokens. Import order controlled via `styles.css`.

| File | Styles for |
|---|---|
| `tokens.css` | Design tokens (colors, spacing, typography) |
| `base.css` | Base resets and global styles |
| `shell.css` | App shell layout |
| `ui-primitives.css` | Primitive UI element styles |
| `accounts.css` | Account views |
| `admin.css` | Admin panel |
| `alt-strategies.css` | Alternative strategies |
| `analysis.css` | Analysis view |
| `compare.css` | Comparison view |
| `docs.css` | In-app docs |
| `ibkr-paper-monitor.css` | IBKR monitor view |
| `runtime.css` | Runtime status views |

### Assets (`assets/`)

Static JSON assets consumed by the in-app docs renderer.

| File | Content |
|---|---|
| `api.json` | API reference documentation content |
| `finance.json` | Finance/strategy documentation content |
| `software.json` | Software architecture documentation content |

---

## Related References

- [`docs/architecture/nav-guide.md`](../architecture/nav-guide.md) — Task-oriented lookup for where to edit UI code
- [`docs/architecture/service-cookbook.md`](../architecture/service-cookbook.md) — Backend service API reference
- `.github/BOT_ARCHITECTURE_CONVENTIONS.md` — Import boundary rules (backend must not import from `trading/interfaces/`)
