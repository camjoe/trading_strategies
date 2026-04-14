import financeData from "../assets/finance.json";
import softwareData from "../assets/software.json";
import apiData from "../assets/api.json";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type FinanceTerm = {
  term: string;
  group: string;
  use: string;
  definition: string;
};

type SoftwarePackage = {
  name: string;
  group: string;
  purpose: string;
};

type SoftwareProject = {
  name: string;
  description: string;
};

type SoftwareLang = {
  name: string;
  usage: string;
};

type ApiBasic = {
  item: string;
  details: string;
};

type ApiEndpoint = {
  method: string;
  path: string;
  group: string;
  description: string;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function esc(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ---------------------------------------------------------------------------
// Finance card
// ---------------------------------------------------------------------------

const FINANCE_UI_SECTION_MAP: Record<string, string> = {
  "Execution and Risk Controls": "Execution & Risk Controls",
  "Performance and Risk": "Performance & Benchmarking",
  "Options and Volatility": "Options / Derivatives",
  "Backtesting and Validation": "Data & Backtesting Integrity",
  "Technical Analysis": "Technical Signals",
  "Trading Strategies": "Trading Strategies",
  "Asset Classes": "Asset Classes",
  "Areas of Focus": "Asset Classes",
};

const FINANCE_SECTION_ORDER = [
  "Performance & Benchmarking",
  "Execution & Risk Controls",
  "Options / Derivatives",
  "Data & Backtesting Integrity",
  "Technical Signals",
  "Trading Strategies",
  "Asset Classes",
];

const FINANCE_SECTION_HEADERS: Record<string, [string, string]> = {
  "Technical Signals": ["Concept", "Description"],
  "Trading Strategies": ["Strategy", "Description"],
  "Asset Classes": ["Asset Class", "Notes"],
};

const UI_TERM_LABELS: Record<string, string> = {
  DTE: "DTE (Days to Expiration)",
};

const TRADING_STRATEGIES_EVAL_LIST = `      <p class="ref-subsection-label">Evaluation Framework</p>
      <ul class="ref-eval-list">
        <li>Universe and timeframe</li>
        <li>Signal definition</li>
        <li>Entry / exit rules</li>
        <li>Position sizing</li>
        <li>Transaction cost and slippage assumptions</li>
        <li>Risk limits</li>
        <li>Validation method (walk-forward, out-of-sample)</li>
        <li>Metrics: Sharpe ratio, max drawdown, turnover, hit rate</li>
      </ul>`;

function buildFinanceSection(title: string, terms: FinanceTerm[]): string {
  const [col1, col2] = FINANCE_SECTION_HEADERS[title] ?? ["Term", "Definition"];
  const rows = terms
    .map((t) => {
      const label = esc(UI_TERM_LABELS[t.term] ?? t.term);
      const def = esc(t.definition);
      return `          <tr><td>${label}</td><td>${def}</td></tr>`;
    })
    .join("\n");

  const extra = title === "Trading Strategies" ? `\n${TRADING_STRATEGIES_EVAL_LIST}` : "";

  return `    <div class="ref-section">
      <h3>${esc(title)}</h3>
      <table class="ref-table ref-table--software">
        <thead><tr><th>${esc(col1)}</th><th>${esc(col2)}</th></tr></thead>
        <tbody>
${rows}
        </tbody>
      </table>${extra}
    </div>`;
}

function buildFinanceCard(): string {
  const terms = (financeData.terms as FinanceTerm[]).filter(
    (t) => t.use === "both" || t.use === "ui",
  );

  const bySection: Record<string, FinanceTerm[]> = {};
  for (const term of terms) {
    const section = FINANCE_UI_SECTION_MAP[term.group];
    if (!section) continue;
    (bySection[section] ??= []).push(term);
  }

  const sections = FINANCE_SECTION_ORDER.filter((s) => bySection[s]?.length)
    .map((s) => buildFinanceSection(s, bySection[s]))
    .join("\n\n");

  return `  <section class="card ref-card">
    <div class="ref-card-head">
      <h2>Financial &amp; Market Knowledge</h2>
      <button type="button" class="ref-card-toggle-all" data-ref-card-toggle-all>Expand all</button>
    </div>

${sections}
  </section>`;
}

// ---------------------------------------------------------------------------
// Software card
// ---------------------------------------------------------------------------

const SOFTWARE_PACKAGE_GROUP_ORDER = [
  "Data & Market Access",
  "Analysis & Modeling",
  "Visualization",
  "Backend & Validation",
  "Developer Tooling",
];

function buildPackagesSection(packages: SoftwarePackage[]): string {
  const grouped: Record<string, SoftwarePackage[]> = {};
  for (const pkg of packages) {
    (grouped[pkg.group] ??= []).push(pkg);
  }

  const orderedGroups = [
    ...SOFTWARE_PACKAGE_GROUP_ORDER.filter((g) => grouped[g]),
    ...Object.keys(grouped)
      .filter((g) => !SOFTWARE_PACKAGE_GROUP_ORDER.includes(g))
      .sort(),
  ];

  const parts = orderedGroups.map((group) => {
    const rows = grouped[group]
      .map((p) => `          <tr><td>${esc(p.name)}</td><td>${esc(p.purpose)}</td></tr>`)
      .join("\n");
    return `      <p class="ref-subsection-label">${esc(group)}</p>
      <table class="ref-table ref-table--software">
        <thead><tr><th>Package</th><th>Purpose</th></tr></thead>
        <tbody>
${rows}
        </tbody>
      </table>`;
  });

  return `    <div class="ref-section">
      <h3>Key Python Packages</h3>
${parts.join("\n\n")}
    </div>`;
}

function buildSoftwareCard(): string {
  const projects = softwareData.projects as SoftwareProject[];
  const langs = softwareData.languages_frameworks as SoftwareLang[];
  const packages = softwareData.packages as SoftwarePackage[];

  const projectRows = projects
    .map((p) => `          <tr><td>${esc(p.name)}</td><td>${esc(p.description)}</td></tr>`)
    .join("\n");

  const langRows = langs
    .map((l) => `          <tr><td>${esc(l.name)}</td><td>${esc(l.usage)}</td></tr>`)
    .join("\n");

  return `  <section class="card ref-card">
    <div class="ref-card-head">
      <h2>Software</h2>
      <button type="button" class="ref-card-toggle-all" data-ref-card-toggle-all>Expand all</button>
    </div>

    <div class="ref-section">
      <h3>Projects in This Repository</h3>
      <table class="ref-table ref-table--software">
        <thead><tr><th>Project</th><th>Description</th></tr></thead>
        <tbody>
${projectRows}
        </tbody>
      </table>
    </div>

    <div class="ref-section">
      <h3>Languages and Frameworks</h3>
      <table class="ref-table ref-table--software">
        <thead><tr><th>Language / Framework</th><th>Usage</th></tr></thead>
        <tbody>
${langRows}
        </tbody>
      </table>
    </div>

${buildPackagesSection(packages)}
  </section>`;
}

// ---------------------------------------------------------------------------
// API card
// ---------------------------------------------------------------------------

const API_GROUP_ORDER = [
  "Accounts & Snapshots Endpoints",
  "Analysis Endpoints",
  "Trading & Signals Endpoints",
  "Admin Endpoints",
  "Logs Endpoints",
  "Backtesting Endpoints",
];

// Static content: request body model tables (not yet extracted to JSON).
const ACCOUNTS_REQUEST_BODY_CONTENT = `
      <p class="ref-subsection-label">PATCH /api/accounts/{account_name}/params (AccountParamsRequest)</p>
      <p class="muted">
        Canonical editable-field definitions live in
        <code>paper_trading_ui/backend/schemas.py</code> (<code>AccountParamsRequest</code>)
        and <code>paper_trading_ui/backend/account_contract.py</code>. The UI groups
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
        and <code>paper_trading_ui/backend/account_contract.py</code>. This summary
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
      <p class="ref-subsection-label">POST /api/accounts/{account_name}/trades (ManualTradeRequest)</p>
      <table class="ref-table">
        <thead><tr><th>Field</th><th>Type / Default</th><th>Notes</th></tr></thead>
        <tbody>
          <tr><td>ticker</td><td>string (required)</td><td>Ticker is normalized to uppercase and validated against recent market data.</td></tr>
          <tr><td>side</td><td>"buy" | "sell"</td><td>Manual trades are only permitted on the virtual test account.</td></tr>
          <tr><td>qty</td><td>float (&gt; 0)</td><td>Position quantity.</td></tr>
          <tr><td>price</td><td>float (&gt; 0)</td><td>Manual execution price.</td></tr>
          <tr><td>fee</td><td>float, default 0.0</td><td>Optional execution fee.</td></tr>
        </tbody>
      </table>

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
    .map((e) => {
      const methodPath = esc(`${e.method} ${e.path}`);
      const desc = esc(e.description);
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

function buildApiCard(): string {
  const basics = (apiData.api_basics as ApiBasic[])
    .map((b) => `          <tr><td>${esc(b.item)}</td><td>${esc(b.details)}</td></tr>`)
    .join("\n");

  const endpoints = apiData.endpoints as ApiEndpoint[];

  const grouped: Record<string, ApiEndpoint[]> = {};
  for (const ep of endpoints) {
    if (!ep.group) continue;
    (grouped[ep.group] ??= []).push(ep);
  }
  for (const group of Object.keys(grouped)) {
    grouped[group].sort((a, b) => a.path.localeCompare(b.path) || a.method.localeCompare(b.method));
  }

  const orderedGroups = [
    ...API_GROUP_ORDER.filter((g) => grouped[g]),
    ...Object.keys(grouped)
      .filter((g) => !API_GROUP_ORDER.includes(g))
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
      <button type="button" class="ref-card-toggle-all" data-ref-card-toggle-all>Expand all</button>
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

// ---------------------------------------------------------------------------
// Public entry point
// ---------------------------------------------------------------------------

export function buildDocsTemplate(): string {
  return `<div id="tab-docs" class="tab-panel layout" hidden>
${buildFinanceCard()}

${buildSoftwareCard()}

${buildApiCard()}
</div>`;
}
