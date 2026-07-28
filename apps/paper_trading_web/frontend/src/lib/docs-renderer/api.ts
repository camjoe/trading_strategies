import apiData from "../../assets/api.json";
import { esc } from "./shared";
import type { ApiBasic, ApiEndpoint } from "./types";

const API_GROUP_ORDER = [
  "Accounts & Snapshots Endpoints",
  "Analysis Endpoints",
  "Trading & Signals Endpoints",
  "Admin Endpoints",
  "Logs Endpoints",
  "Backtesting Endpoints",
];

const ACCOUNTS_REQUEST_BODY_CONTENT = `
      <p class="ref-subsection-label">PATCH /api/accounts/{account_name}/params (AccountParamsRequest)</p>
      <p class="muted">
        Canonical editable-field definitions live in
        <code>paper_trading_ui/backend/schemas.py</code> (<code>AccountParamsRequest</code>)
        , <code>paper_trading_ui/backend/account_contract.py</code>, and
        <code>GET /api/accounts/config/options</code>. The UI groups
        those fields into the sections below instead of restating the full field-by-field
        wire contract here.
      </p>
      <table class="ref-table">
        <thead><tr><th>Field Group</th><th>Coverage</th><th>Notes</th></tr></thead>
        <tbody>
          <tr><td>Core policy</td><td>Identity, risk policy, sizing, instrument mode, learning flag</td><td>Only supplied non-null fields are applied.</td></tr>
          <tr><td>Goals</td><td>Operator-facing return targets and goal period</td><td>Lets the UI update account goals without recreating the account.</td></tr>
          <tr><td>Options / LEAPs</td><td>Selection filters, DTE bounds, delta and IV gates, premium and loss controls</td><td>Used for LEAPs/options-aware account policies.</td></tr>
          <tr><td>Rotation</td><td>Schedule, regime mapping, overlay thresholds, active state</td><td>Supports both scheduled rotation and regime-overlay controls.</td></tr>
        </tbody>
      </table>

      <p class="ref-subsection-label">Important response fields on account endpoints</p>
      <table class="ref-table">
        <thead><tr><th>Field</th><th>Where it appears</th><th>Notes</th></tr></thead>
        <tbody>
          <tr><td>liveBenchmarkReturnPct</td><td>GET /api/accounts/compare</td><td>Benchmark return over the same persisted live snapshot period when enough history exists.</td></tr>
          <tr><td>liveAlphaPct</td><td>GET /api/accounts/compare</td><td>Live account return minus benchmark return over the aligned snapshot period.</td></tr>
          <tr><td>liveBenchmarkOverlay</td><td>GET /api/accounts/{account_name}</td><td>Time-aligned benchmark overlay payload with benchmark ticker, summary stats, and chart-ready points.</td></tr>
          <tr><td>latestBacktestMetrics</td><td>GET /api/accounts/{account_name}, GET /api/accounts/compare</td><td>Compact backtest metric bundle used by the UI for ratio and quality summaries.</td></tr>
        </tbody>
      </table>`;

const ADMIN_REQUEST_BODY_CONTENT = `
      <p class="ref-subsection-label">POST /api/admin/accounts/create (AdminCreateAccountRequest)</p>
      <p class="muted">
        Canonical create-field definitions live in
        <code>paper_trading_ui/backend/schemas.py</code> (<code>AdminCreateAccountRequest</code>)
        , <code>paper_trading_ui/backend/account_contract.py</code>, and
        <code>GET /api/accounts/config/options</code>. This summary
        focuses on grouped intent rather than repeating the full contract.
      </p>
      <table class="ref-table">
        <thead><tr><th>Field Group</th><th>Coverage</th><th>Notes</th></tr></thead>
        <tbody>
          <tr><td>Identity</td><td>name, strategy, initialCash, benchmarkTicker, descriptiveName</td><td>Core account identity and display fields.</td></tr>
          <tr><td>Policy and goals</td><td>Risk policy, sizing, learning, return goals</td><td>Mirrors the editable account-config surface used by the detail UI.</td></tr>
          <tr><td>Options / LEAPs</td><td>Option selection bounds, delta and IV filters, premium and loss controls</td><td>Relevant when the account uses LEAPs-aware execution.</td></tr>
          <tr><td>Rotation</td><td>Enablement, cadence, schedule, regime mapping, overlays, active state</td><td>Uses the same canonical rotation-profile mapping as account updates.</td></tr>
        </tbody>
      </table>

      <p class="ref-subsection-label">POST /api/admin/accounts/delete (AdminDeleteAccountRequest)</p>
      <table class="ref-table">
        <thead><tr><th>Field</th><th>Type / Default</th><th>Notes</th></tr></thead>
        <tbody>
          <tr><td>accountName</td><td>string (required)</td><td>Name of the account to delete.</td></tr>
          <tr><td>confirm</td><td>bool, default false</td><td>Must be true or the request is rejected with 400.</td></tr>
        </tbody>
      </table>`;

const TRADING_SIGNALS_REQUEST_BODY_CONTENT = `
      <p class="ref-subsection-label">POST /api/features/signals (FeatureSignalsRequest)</p>
      <table class="ref-table">
        <thead><tr><th>Field</th><th>Type / Default</th><th>Notes</th></tr></thead>
        <tbody>
          <tr><td>ticker</td><td>string (required)</td><td>Runs the UI signal helpers for the requested ticker and returns provider-specific reasoning/context.</td></tr>
        </tbody>
      </table>`;

const BACKTEST_REQUEST_BODY_SECTION = `    <div class="ref-section">
      <h3>Request Body Models</h3>

      <p class="ref-subsection-label">POST /api/backtests/run (BacktestRunRequest)</p>
      <table class="ref-table">
        <thead><tr><th>Field</th><th>Type / Default</th><th>Notes</th></tr></thead>
        <tbody>
          <tr><td>account</td><td>string (required)</td><td>Account name to run against.</td></tr>
          <tr><td>tickersFile</td><td>string, default trading/config/trade_universe.txt</td><td>Ticker universe file path.</td></tr>
          <tr><td>universeHistoryDir</td><td>string | null</td><td>Optional point-in-time universe history directory.</td></tr>
          <tr><td>start / end</td><td>string | null</td><td>Optional ISO date boundaries.</td></tr>
          <tr><td>lookbackMonths</td><td>int | null, &gt; 0</td><td>Optional lookback window if dates are omitted.</td></tr>
          <tr><td>slippageBps</td><td>float, default 5.0</td><td>Per-trade slippage in basis points.</td></tr>
          <tr><td>fee</td><td>float, default 0.0</td><td>Flat per-trade fee.</td></tr>
          <tr><td>runName</td><td>string | null</td><td>Optional custom run name.</td></tr>
          <tr><td>allowApproximateLeaps</td><td>bool, default false</td><td>Allow fallback approximation for LEAP pricing if exact data is missing.</td></tr>
        </tbody>
      </table>

      <p class="ref-subsection-label">POST /api/backtests/preflight (BacktestPreflightRequest)</p>
      <table class="ref-table">
        <thead><tr><th>Field</th><th>Type / Default</th><th>Notes</th></tr></thead>
        <tbody>
          <tr><td>account</td><td>string (required)</td><td>Account name to validate.</td></tr>
          <tr><td>tickersFile</td><td>string, default trading/config/trade_universe.txt</td><td>Ticker universe file path.</td></tr>
          <tr><td>universeHistoryDir</td><td>string | null</td><td>Optional point-in-time universe history directory.</td></tr>
          <tr><td>start / end</td><td>string | null</td><td>Optional ISO date boundaries.</td></tr>
          <tr><td>lookbackMonths</td><td>int | null, &gt; 0</td><td>Optional lookback window.</td></tr>
          <tr><td>allowApproximateLeaps</td><td>bool, default false</td><td>Same fallback toggle used by run endpoints.</td></tr>
        </tbody>
      </table>

      <p class="ref-subsection-label">POST /api/backtests/walk-forward (WalkForwardRunRequest)</p>
      <table class="ref-table">
        <thead><tr><th>Field</th><th>Type / Default</th><th>Notes</th></tr></thead>
        <tbody>
          <tr><td>account</td><td>string (required)</td><td>Account name to run against.</td></tr>
          <tr><td>tickersFile</td><td>string, default trading/config/trade_universe.txt</td><td>Ticker universe file path.</td></tr>
          <tr><td>universeHistoryDir</td><td>string | null</td><td>Optional point-in-time universe history directory.</td></tr>
          <tr><td>start / end</td><td>string | null</td><td>Optional ISO date boundaries.</td></tr>
          <tr><td>lookbackMonths</td><td>int | null, &gt; 0</td><td>Training lookback window.</td></tr>
          <tr><td>testMonths</td><td>int, default 1, &gt; 0</td><td>Length of each test window.</td></tr>
          <tr><td>stepMonths</td><td>int, default 1, &gt; 0</td><td>How far to roll forward between windows.</td></tr>
          <tr><td>slippageBps</td><td>float, default 5.0</td><td>Per-trade slippage in basis points.</td></tr>
          <tr><td>fee</td><td>float, default 0.0</td><td>Flat per-trade fee.</td></tr>
          <tr><td>runNamePrefix</td><td>string | null</td><td>Optional naming prefix for generated window runs.</td></tr>
          <tr><td>allowApproximateLeaps</td><td>bool, default false</td><td>Allow LEAP approximation fallback.</td></tr>
        </tbody>
      </table>

      <p class="ref-subsection-label">Key backtest result metrics used in the UI</p>
      <table class="ref-table">
        <thead><tr><th>Field</th><th>Meaning</th><th>Where the UI uses it</th></tr></thead>
        <tbody>
          <tr><td>sharpeRatio</td><td>Risk-adjusted return using total volatility.</td><td>Backtest run results, latest backtest summary, and compare table.</td></tr>
          <tr><td>sortinoRatio</td><td>Risk-adjusted return using downside volatility only.</td><td>Backtest result views and persisted report payloads.</td></tr>
          <tr><td>calmarRatio</td><td>Return relative to max drawdown.</td><td>Backtest result views and persisted report payloads.</td></tr>
          <tr><td>winRatePct</td><td>Percent of profitable trades.</td><td>Latest backtest cards and compare table.</td></tr>
          <tr><td>profitFactor</td><td>Gross profits divided by gross losses.</td><td>Latest backtest cards and compare table.</td></tr>
          <tr><td>avgTradeReturnPct</td><td>Average return per trade.</td><td>Persisted report payloads and detailed backtest summaries.</td></tr>
          <tr><td>benchmarkReturnPct / alphaPct</td><td>Benchmark-relative context for the same backtest window.</td><td>Backtest result summary and account comparison views.</td></tr>
        </tbody>
      </table>
    </div>`;

function buildApiSection(title: string, endpoints: ApiEndpoint[], extra: string): string {
  const rows = endpoints
    .map((endpoint) => {
      const methodPath = esc(`${endpoint.method} ${endpoint.path}`);
      const desc = esc(endpoint.description);
      return `          <tr><td>${methodPath}</td><td>${desc}</td></tr>`;
    })
    .join("\n");

  return `    <div class="ref-section">
      <h3>${esc(title)}</h3>
      <table class="ref-table ref-table--endpoint">
        <thead><tr><th>Method + Path</th><th>Purpose</th></tr></thead>
        <tbody>
${rows}
        </tbody>
      </table>${extra}
    </div>`;
}

export function buildApiCard(): string {
  const basics = (apiData.api_basics as ApiBasic[])
    .map((basic) => `          <tr><td>${esc(basic.item)}</td><td>${esc(basic.details)}</td></tr>`)
    .join("\n");

  const endpoints = apiData.endpoints as ApiEndpoint[];

  const grouped: Record<string, ApiEndpoint[]> = {};
  for (const endpoint of endpoints) {
    if (!endpoint.group) continue;
    (grouped[endpoint.group] ??= []).push(endpoint);
  }
  for (const group of Object.keys(grouped)) {
    grouped[group].sort((a, b) => a.path.localeCompare(b.path) || a.method.localeCompare(b.method));
  }

  const orderedGroups = [
    ...API_GROUP_ORDER.filter((group) => grouped[group]),
    ...Object.keys(grouped)
      .filter((group) => !API_GROUP_ORDER.includes(group))
      .sort(),
  ];

  const endpointSections = orderedGroups
    .map((group) => {
      const extra =
        group === "Accounts & Snapshots Endpoints"
          ? ACCOUNTS_REQUEST_BODY_CONTENT
          : group === "Trading & Signals Endpoints"
            ? TRADING_SIGNALS_REQUEST_BODY_CONTENT
            : group === "Admin Endpoints"
              ? ADMIN_REQUEST_BODY_CONTENT
              : "";
      return buildApiSection(group, grouped[group], extra);
    })
    .join("\n\n");

  return `  <section class="card ref-card">
    <div class="ref-card-head">
      <h2>API Reference</h2>
      <button type="button" class="ref-card-toggle-all" data-ref-card-toggle-all aria-label="Expand all" data-tooltip="Expand all">+</button>
    </div>

    <div class="ref-section">
      <h3>API Basics</h3>
      <p class="ref-note">Full interactive docs with parameters, schemas, and live requests: <a href="/docs" target="_blank" rel="noopener">/docs</a> (Swagger UI) &mdash; <a href="/redoc" target="_blank" rel="noopener">/redoc</a> (ReDoc)</p>
      <table class="ref-table ref-table--endpoint">
        <thead><tr><th>Item</th><th>Details</th></tr></thead>
        <tbody>
${basics}
        </tbody>
      </table>
    </div>

${endpointSections}

${BACKTEST_REQUEST_BODY_SECTION}
  </section>`;
}
