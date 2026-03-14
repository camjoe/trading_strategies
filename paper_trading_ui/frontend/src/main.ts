import "./styles.css";

type AccountSummary = {
  name: string;
  displayName: string;
  strategy: string;
  instrumentMode: string;
  benchmark: string;
  initialCash: number;
  equity: number;
  totalChange: number;
  totalChangePct: number;
  changeSinceLastSnapshot: number | null;
  latestSnapshotTime: string | null;
};

type AccountDetail = {
  account: AccountSummary;
  latestBacktest: BacktestRunSummary | null;
  snapshots: Array<{
    time: string;
    cash: number;
    marketValue: number;
    equity: number;
    realizedPnl: number;
    unrealizedPnl: number;
  }>;
  trades: Array<{
    ticker: string;
    side: string;
    qty: number;
    price: number;
    fee: number;
    tradeTime: string;
  }>;
};

type BacktestRunSummary = {
  runId: number;
  runName: string | null;
  accountName: string;
  strategy: string;
  startDate: string;
  endDate: string;
  createdAt: string;
  slippageBps: number;
  feePerTrade: number;
  tickersFile: string;
};

type BacktestRunResult = {
  runId: number;
  accountName: string;
  startDate: string;
  endDate: string;
  tradeCount: number;
  endingEquity: number;
  totalReturnPct: number;
  benchmarkReturnPct: number | null;
  alphaPct: number | null;
  maxDrawdownPct: number;
  warnings: string[];
};

type WalkForwardResult = {
  accountName: string;
  startDate: string;
  endDate: string;
  windowCount: number;
  runIds: number[];
  averageReturnPct: number;
  medianReturnPct: number;
  bestReturnPct: number;
  worstReturnPct: number;
};

type BacktestReport = {
  run_id: number;
  run_name: string | null;
  account_name: string;
  strategy: string;
  benchmark_ticker: string;
  start_date: string;
  end_date: string;
  created_at: string;
  slippage_bps: number;
  fee_per_trade: number;
  tickers_file: string;
  notes: string | null;
  warnings: string;
  trade_count: number;
  starting_equity: number;
  ending_equity: number;
  total_return_pct: number;
  max_drawdown_pct: number;
};

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";
let cachedAccounts: AccountSummary[] = [];

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) {
  throw new Error("Missing #app root");
}
const appRoot: HTMLDivElement = app;

const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

function pct(v: number): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function num(v: number): string {
  return `${v >= 0 ? "+" : ""}${currency.format(v)}`;
}

function esc(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function classifyLogLine(line: string): string {
  const upper = line.toUpperCase();
  if (upper.includes("ERROR") || upper.includes("FAILED") || upper.includes("EXCEPTION") || upper.includes("TRACEBACK")) {
    return "error";
  }
  if (upper.includes("WARN")) {
    return "warn";
  }
  if (upper.includes("DONE") || upper.includes("COMPLETE") || upper.includes("SUCCESS")) {
    return "ok";
  }
  if (upper.includes("START") || upper.includes("RUN META")) {
    return "meta";
  }
  return "plain";
}

function sanitizeLogLine(line: string): string {
  // Remove BOM, ANSI escape codes, and low control chars that can render as artifacts.
  return line
    .replace(/^\uFEFF/, "")
    .replace(/\u001B\[[0-9;]*[A-Za-z]/g, "")
    .replace(/\r/g, "")
    .replace(/[\uFFFD]/g, "")
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "");
}

function renderLogLines(lines: string[]): string {
  const cleaned = lines.map(sanitizeLogLine).filter((line) => line.trim().length > 0);

  if (!cleaned.length) {
    return `<div class="log-empty">No lines matched this filter.</div>`;
  }

  let html = "";
  let inGroup = false;

  const closeGroup = (): void => {
    if (inGroup) {
      html += "</details>";
      inGroup = false;
    }
  };

  for (const line of cleaned) {
    const kind = classifyLogLine(line);

    if (kind === "meta") {
      closeGroup();
      html += `<details class="log-group" open><summary class="log-meta-line">${esc(line)}</summary>`;
      inGroup = true;
      continue;
    }

    if (!inGroup) {
      html += `<div class="log-line log-${kind}"><span class="log-text">${esc(line)}</span></div>`;
      continue;
    }

    html += `<div class="log-line log-${kind}"><span class="log-text">${esc(line)}</span></div>`;
  }

  closeGroup();
  return html;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

async function postJson<T>(path: string, payload?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: payload ? { "Content-Type": "application/json" } : undefined,
    body: payload ? JSON.stringify(payload) : undefined,
  });
  if (!res.ok) {
    let detail = "";
    try {
      const maybeJson = (await res.json()) as { detail?: string };
      detail = typeof maybeJson.detail === "string" ? maybeJson.detail : "";
    } catch {
      detail = "";
    }
    throw new Error(detail ? `Request failed: ${res.status} (${detail})` : `Request failed: ${res.status}`);
  }
  const text = await res.text();
  return (text ? (JSON.parse(text) as T) : ({} as T));
}

function renderShell(): void {
  const root = appRoot;
  root.innerHTML = `
    <header class="topbar">
      <h1>Paper Trading Console</h1>
      <div class="actions">
        <button id="refreshAccountsBtn">Refresh Accounts</button>
        <button id="snapshotAllBtn">Snapshot All</button>
      </div>
    </header>

    <main class="layout">
      <section class="card accounts-card">
        <h2>Accounts</h2>
        <div id="accountsGrid" class="accounts-grid"></div>
      </section>

      <section class="card detail-card">
        <h2>Account Detail</h2>
        <div id="accountDetail" class="empty">Choose an account to inspect snapshots and trades.</div>
      </section>

      <section class="card logs-card">
        <h2>Logs</h2>
        <div class="log-controls">
          <select id="logFileSelect"></select>
          <input id="logFilterInput" placeholder="Filter text" />
          <button id="loadLogBtn">Load Log</button>
        </div>
        <div id="logOutput" class="log-output">Select a log file to begin.</div>
      </section>

      <section class="card backtest-card">
        <h2>Backtesting</h2>

        <div class="bt-grid">
          <article>
            <h3>Run Backtest</h3>
            <form id="runBacktestForm" class="bt-form">
              <select id="backtestAccountSelect" name="account" required>
                <option value="">Select account</option>
              </select>
              <input name="tickersFile" value="trading/trade_universe.txt" placeholder="Tickers file" />
              <input name="universeHistoryDir" placeholder="Universe history dir (optional)" />
              <div class="bt-quick-buttons" data-target-form="runBacktestForm">
                <button type="button" data-lookback-months="1">Last 1M</button>
                <button type="button" data-lookback-months="3">Last 3M</button>
                <button type="button" data-lookback-months="6">Last 6M</button>
                <button type="button" data-lookback-months="12">Last 12M</button>
              </div>
              <div class="bt-row">
                <input name="start" type="date" placeholder="Start" />
                <input name="end" type="date" placeholder="End" />
              </div>
              <div class="bt-row">
                <input name="lookbackMonths" type="number" min="1" placeholder="Lookback months" />
                <input name="slippageBps" type="number" step="0.1" value="5" placeholder="Slippage bps" />
              </div>
              <div class="bt-row">
                <input name="fee" type="number" step="0.01" value="0" placeholder="Fee" />
                <input name="runName" placeholder="Run name (optional)" />
              </div>
              <label class="bt-check"><input name="allowApproximateLeaps" type="checkbox" /> Allow approximate LEAPs</label>
              <button type="submit">Run Backtest</button>
            </form>
            <div id="backtestRunOutput" class="empty">Submit to run a backtest.</div>
          </article>

          <article>
            <h3>Run Walk-Forward</h3>
            <form id="runWalkForwardForm" class="bt-form">
              <select id="walkForwardAccountSelect" name="account" required>
                <option value="">Select account</option>
              </select>
              <input name="tickersFile" value="trading/trade_universe.txt" placeholder="Tickers file" />
              <input name="universeHistoryDir" placeholder="Universe history dir (optional)" />
              <div class="bt-quick-buttons" data-target-form="runWalkForwardForm">
                <button type="button" data-lookback-months="3">Last 3M</button>
                <button type="button" data-lookback-months="6">Last 6M</button>
                <button type="button" data-lookback-months="12">Last 12M</button>
                <button type="button" data-lookback-months="24">Last 24M</button>
              </div>
              <div class="bt-row">
                <input name="start" type="date" placeholder="Start" />
                <input name="end" type="date" placeholder="End" />
              </div>
              <div class="bt-row">
                <input name="lookbackMonths" type="number" min="1" placeholder="Lookback months" />
                <input name="testMonths" type="number" min="1" value="1" placeholder="Test months" />
              </div>
              <div class="bt-row">
                <input name="stepMonths" type="number" min="1" value="1" placeholder="Step months" />
                <input name="slippageBps" type="number" step="0.1" value="5" placeholder="Slippage bps" />
              </div>
              <div class="bt-row">
                <input name="fee" type="number" step="0.01" value="0" placeholder="Fee" />
                <input name="runNamePrefix" placeholder="Run name prefix (optional)" />
              </div>
              <label class="bt-check"><input name="allowApproximateLeaps" type="checkbox" /> Allow approximate LEAPs</label>
              <button type="submit">Run Walk-Forward</button>
            </form>
            <div id="walkForwardOutput" class="empty">Submit to run walk-forward windows.</div>
          </article>
        </div>

        <div class="bt-grid">
          <article>
            <div class="bt-head">
              <h3>Backtest Runs</h3>
              <button id="refreshBacktestsBtn">Refresh Runs</button>
            </div>
            <div id="backtestRunsList" class="bt-runs empty">No runs loaded.</div>
          </article>

          <article>
            <h3>Run Report</h3>
            <div id="backtestReportView" class="empty">Choose a run to inspect report details.</div>
          </article>
        </div>
      </section>
    </main>
  `;
}

function accountCard(a: AccountSummary): string {
  const pnlClass = a.totalChange >= 0 ? "up" : "down";
  const latestSnapshot = a.latestSnapshotTime ? new Date(a.latestSnapshotTime).toLocaleString() : "none";
  const snapshotChange = a.changeSinceLastSnapshot === null ? "n/a" : num(a.changeSinceLastSnapshot);

  return `
    <button class="account-card" data-account="${esc(a.name)}">
      <div class="row top">
        <strong>${esc(a.displayName)}</strong>
        <span class="chip">${esc(a.strategy)}</span>
      </div>
      <div class="row slim">Name: ${esc(a.name)} | Benchmark: ${esc(a.benchmark)}</div>
      <div class="row">
        <span>Equity</span>
        <strong>${currency.format(a.equity)}</strong>
      </div>
      <div class="row ${pnlClass}">
        <span>Total Change</span>
        <strong>${num(a.totalChange)} (${pct(a.totalChangePct)})</strong>
      </div>
      <div class="row slim">
        <span>Since Last Snapshot: ${snapshotChange}</span>
      </div>
      <div class="row slim">
        <span>Last Snapshot: ${latestSnapshot}</span>
      </div>
    </button>
  `;
}

function populateBacktestAccountSelects(accounts: AccountSummary[]): void {
  const accountOptions = accounts
    .map((a) => `<option value="${esc(a.name)}">${esc(a.displayName)} (${esc(a.name)})</option>`)
    .join("");

  for (const selectId of ["#backtestAccountSelect", "#walkForwardAccountSelect"]) {
    const select = document.querySelector<HTMLSelectElement>(selectId);
    if (!select) continue;
    const previous = select.value;
    select.innerHTML = `<option value="">Select account</option>${accountOptions}`;
    if (previous && accounts.some((a) => a.name === previous)) {
      select.value = previous;
    }
  }
}

function applyBacktestAccountDefaults(form: HTMLFormElement | null, accountName: string): void {
  if (!form || !accountName) return;
  const account = cachedAccounts.find((a) => a.name === accountName);
  if (!account) return;

  const leapsCheckbox = form.querySelector<HTMLInputElement>('input[name="allowApproximateLeaps"]');
  if (!leapsCheckbox) return;
  leapsCheckbox.checked = account.instrumentMode === "leaps";
}

async function loadAccounts(): Promise<void> {
  const target = document.querySelector<HTMLDivElement>("#accountsGrid");
  if (!target) return;

  target.innerHTML = `<div class="empty">Loading accounts...</div>`;
  const data = await getJson<{ accounts: AccountSummary[] }>("/api/accounts");
  cachedAccounts = data.accounts;
  populateBacktestAccountSelects(cachedAccounts);

  if (!data.accounts.length) {
    target.innerHTML = `<div class="empty">No accounts found in the paper trading database.</div>`;
    return;
  }

  target.innerHTML = data.accounts.map(accountCard).join("");

  for (const btn of document.querySelectorAll<HTMLButtonElement>(".account-card")) {
    btn.addEventListener("click", async () => {
      const accountName = btn.dataset.account;
      if (!accountName) return;
      await loadAccountDetail(accountName);
    });
  }
}

function renderDetail(detail: AccountDetail): string {
  const snapRows = detail.snapshots
    .slice(0, 25)
    .map(
      (s) => `
      <tr>
        <td>${new Date(s.time).toLocaleString()}</td>
        <td>${currency.format(s.equity)}</td>
        <td>${currency.format(s.cash)}</td>
        <td>${currency.format(s.marketValue)}</td>
      </tr>
    `,
    )
    .join("");

  const tradeRows = detail.trades
    .slice(-25)
    .reverse()
    .map(
      (t) => `
      <tr>
        <td>${new Date(t.tradeTime).toLocaleString()}</td>
        <td>${esc(t.ticker)}</td>
        <td class="${t.side === "buy" ? "up" : "down"}">${esc(t.side)}</td>
        <td>${t.qty.toFixed(4)}</td>
        <td>${currency.format(t.price)}</td>
        <td>${currency.format(t.fee)}</td>
      </tr>
    `,
    )
    .join("");

  const latestBacktest = detail.latestBacktest
    ? `
      <div class="bt-result">
        <div><strong>Latest Backtest Run ${detail.latestBacktest.runId}</strong> ${esc(detail.latestBacktest.runName ?? "(unnamed)")}</div>
        <div>Range: ${esc(detail.latestBacktest.startDate)}..${esc(detail.latestBacktest.endDate)} | Created: ${new Date(detail.latestBacktest.createdAt).toLocaleString()}</div>
        <div>Slippage: ${detail.latestBacktest.slippageBps.toFixed(2)} bps | Fee: ${currency.format(detail.latestBacktest.feePerTrade)}</div>
        <button id="openLatestBacktestReportBtn" data-run-id="${detail.latestBacktest.runId}" type="button">Open Report</button>
      </div>
    `
    : `<div class="empty">No backtest run found for this account yet.</div>`;

  return `
    <div class="detail-head">
      <div>
        <h3>${esc(detail.account.displayName)}</h3>
        <p>${esc(detail.account.name)} | ${esc(detail.account.strategy)} | ${esc(detail.account.benchmark)}</p>
      </div>
      <button id="snapshotOneBtn" data-account="${esc(detail.account.name)}">Snapshot This Account</button>
    </div>

    <article>
      <h4>Latest Backtest</h4>
      ${latestBacktest}
    </article>

    <div class="detail-grid">
      <article>
        <h4>Equity Snapshots</h4>
        <table>
          <thead><tr><th>Time</th><th>Equity</th><th>Cash</th><th>Market Value</th></tr></thead>
          <tbody>${snapRows || `<tr><td colspan="4">No snapshots yet.</td></tr>`}</tbody>
        </table>
      </article>

      <article>
        <h4>Recent Trades</h4>
        <table>
          <thead><tr><th>Time</th><th>Ticker</th><th>Side</th><th>Qty</th><th>Price</th><th>Fee</th></tr></thead>
          <tbody>${tradeRows || `<tr><td colspan="6">No trades yet.</td></tr>`}</tbody>
        </table>
      </article>
    </div>
  `;
}

async function loadAccountDetail(accountName: string): Promise<void> {
  const target = document.querySelector<HTMLDivElement>("#accountDetail");
  if (!target) return;

  target.innerHTML = `<div class="empty">Loading ${esc(accountName)}...</div>`;
  const detail = await getJson<AccountDetail>(`/api/accounts/${encodeURIComponent(accountName)}`);
  target.innerHTML = renderDetail(detail);

  const snapBtn = document.querySelector<HTMLButtonElement>("#snapshotOneBtn");
  if (snapBtn) {
    snapBtn.addEventListener("click", async () => {
      const acct = snapBtn.dataset.account;
      if (!acct) return;
      await postJson(`/api/actions/snapshot/${encodeURIComponent(acct)}`);
      await loadAccountDetail(acct);
      await loadAccounts();
    });
  }

  const openReportBtn = document.querySelector<HTMLButtonElement>("#openLatestBacktestReportBtn");
  if (openReportBtn) {
    openReportBtn.addEventListener("click", async () => {
      const runIdRaw = openReportBtn.dataset.runId;
      if (!runIdRaw) return;
      const runId = Number(runIdRaw);
      if (!Number.isFinite(runId)) return;
      await loadBacktestReport(runId);
    });
  }
}

async function loadLogFiles(): Promise<void> {
  const select = document.querySelector<HTMLSelectElement>("#logFileSelect");
  if (!select) return;

  const data = await getJson<{ files: string[] }>("/api/logs/files");
  if (!data.files.length) {
    select.innerHTML = `<option value="">No log files</option>`;
    return;
  }

  select.innerHTML = data.files.map((f) => `<option value="${esc(f)}">${esc(f)}</option>`).join("");
}

async function loadSelectedLog(): Promise<void> {
  const select = document.querySelector<HTMLSelectElement>("#logFileSelect");
  const filterInput = document.querySelector<HTMLInputElement>("#logFilterInput");
  const output = document.querySelector<HTMLElement>("#logOutput");
  if (!select || !output || !filterInput) return;

  const file = select.value;
  if (!file) {
    output.textContent = "No log file selected.";
    return;
  }

  const contains = filterInput.value.trim();
  const query = new URLSearchParams({ limit: "400" });
  if (contains) {
    query.set("contains", contains);
  }

  const data = await getJson<{ lines: string[] }>(`/api/logs/${encodeURIComponent(file)}?${query.toString()}`);
  output.innerHTML = renderLogLines(data.lines);
}

function parseOptInt(raw: string): number | null {
  const v = raw.trim();
  if (!v) return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

function parseOptStr(raw: string): string | null {
  const v = raw.trim();
  return v ? v : null;
}

function validateDateInputs(start: string | null, lookbackMonths: number | null): string | null {
  if (start && lookbackMonths !== null) {
    return "Use either Start date or Lookback months, not both.";
  }
  return null;
}

function renderBacktestRunResult(result: BacktestRunResult): string {
  const benchmarkLine =
    result.benchmarkReturnPct === null || result.alphaPct === null
      ? "Benchmark: unavailable"
      : `Benchmark ${pct(result.benchmarkReturnPct)} | Alpha ${pct(result.alphaPct)}`;
  const warnings = result.warnings.length
    ? `<ul>${result.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>`
    : "<div>Warnings: none</div>";

  return `
    <div class="bt-result">
      <div><strong>Run ${result.runId}</strong> | ${esc(result.accountName)} | ${esc(result.startDate)}..${esc(result.endDate)}</div>
      <div>Trades: ${result.tradeCount} | End Equity: ${currency.format(result.endingEquity)} | Return: ${pct(result.totalReturnPct)} | Max DD: ${pct(result.maxDrawdownPct)}</div>
      <div>${benchmarkLine}</div>
      ${warnings}
    </div>
  `;
}

function renderWalkForwardResult(result: WalkForwardResult): string {
  const runIds = result.runIds.length ? result.runIds.join(", ") : "none";
  return `
    <div class="bt-result">
      <div><strong>${esc(result.accountName)}</strong> | ${esc(result.startDate)}..${esc(result.endDate)} | Windows: ${result.windowCount}</div>
      <div>Avg ${pct(result.averageReturnPct)} | Median ${pct(result.medianReturnPct)} | Best ${pct(result.bestReturnPct)} | Worst ${pct(result.worstReturnPct)}</div>
      <div>Run IDs: ${esc(runIds)}</div>
    </div>
  `;
}

function renderBacktestRunCard(run: BacktestRunSummary): string {
  const created = new Date(run.createdAt).toLocaleString();
  return `
    <button class="bt-run-item" data-run-id="${run.runId}">
      <div class="row top">
        <strong>#${run.runId} ${esc(run.runName ?? "(unnamed)")}</strong>
        <span class="chip">${esc(run.accountName)}</span>
      </div>
      <div class="row slim">${esc(run.strategy)} | ${esc(run.startDate)}..${esc(run.endDate)}</div>
      <div class="row slim">Created: ${created}</div>
    </button>
  `;
}

function renderBacktestReport(report: BacktestReport): string {
  return `
    <div class="bt-result">
      <div><strong>Run ${report.run_id}</strong> ${esc(report.run_name ?? "(unnamed)")} | ${esc(report.account_name)} | ${esc(report.strategy)}</div>
      <div>Range: ${esc(report.start_date)}..${esc(report.end_date)} | Benchmark: ${esc(report.benchmark_ticker)}</div>
      <div>Start: ${currency.format(report.starting_equity)} | End: ${currency.format(report.ending_equity)} | Return: ${pct(report.total_return_pct)} | Max DD: ${pct(report.max_drawdown_pct)}</div>
      <div>Trades: ${report.trade_count} | Slippage: ${report.slippage_bps.toFixed(2)} bps | Fee: ${currency.format(report.fee_per_trade)}</div>
      <div>Warnings: ${esc(report.warnings || "none")}</div>
    </div>
  `;
}

async function loadBacktestRuns(): Promise<void> {
  const target = document.querySelector<HTMLDivElement>("#backtestRunsList");
  if (!target) return;

  target.innerHTML = `<div class="empty">Loading backtest runs...</div>`;
  const data = await getJson<{ runs: BacktestRunSummary[] }>("/api/backtests/runs?limit=100");

  if (!data.runs.length) {
    target.innerHTML = `<div class="empty">No backtest runs found yet.</div>`;
    return;
  }

  target.innerHTML = data.runs.map(renderBacktestRunCard).join("");

  for (const btn of document.querySelectorAll<HTMLButtonElement>(".bt-run-item")) {
    btn.addEventListener("click", async () => {
      const runIdRaw = btn.dataset.runId;
      if (!runIdRaw) return;
      const runId = Number(runIdRaw);
      if (!Number.isFinite(runId)) return;
      await loadBacktestReport(runId);
    });
  }
}

async function loadBacktestReport(runId: number): Promise<void> {
  const target = document.querySelector<HTMLDivElement>("#backtestReportView");
  if (!target) return;

  target.innerHTML = `<div class="empty">Loading report for run ${runId}...</div>`;
  const report = await getJson<BacktestReport>(`/api/backtests/runs/${runId}`);
  target.innerHTML = renderBacktestReport(report);
}

async function wireActions(): Promise<void> {
  const refreshBtn = document.querySelector<HTMLButtonElement>("#refreshAccountsBtn");
  const snapshotAllBtn = document.querySelector<HTMLButtonElement>("#snapshotAllBtn");
  const loadLogBtn = document.querySelector<HTMLButtonElement>("#loadLogBtn");
  const refreshBacktestsBtn = document.querySelector<HTMLButtonElement>("#refreshBacktestsBtn");
  const runBacktestForm = document.querySelector<HTMLFormElement>("#runBacktestForm");
  const runWalkForwardForm = document.querySelector<HTMLFormElement>("#runWalkForwardForm");
  const backtestAccountSelect = document.querySelector<HTMLSelectElement>("#backtestAccountSelect");
  const walkForwardAccountSelect = document.querySelector<HTMLSelectElement>("#walkForwardAccountSelect");

  for (const quickButtons of document.querySelectorAll<HTMLDivElement>(".bt-quick-buttons")) {
    quickButtons.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLButtonElement)) return;

      const monthsRaw = target.dataset.lookbackMonths;
      if (!monthsRaw) return;
      const months = Number(monthsRaw);
      if (!Number.isFinite(months) || months <= 0) return;

      const formId = quickButtons.dataset.targetForm;
      if (!formId) return;
      const form = document.querySelector<HTMLFormElement>(`#${formId}`);
      if (!form) return;

      const lookbackInput = form.querySelector<HTMLInputElement>('input[name="lookbackMonths"]');
      const startInput = form.querySelector<HTMLInputElement>('input[name="start"]');
      const endInput = form.querySelector<HTMLInputElement>('input[name="end"]');
      if (lookbackInput) {
        lookbackInput.value = String(Math.trunc(months));
      }
      if (startInput) {
        startInput.value = "";
      }
      if (endInput) {
        endInput.value = "";
      }
    });
  }

  refreshBtn?.addEventListener("click", () => void loadAccounts());

  snapshotAllBtn?.addEventListener("click", async () => {
    await postJson<{ status: string }>("/api/actions/snapshot-all");
    await loadAccounts();
  });

  loadLogBtn?.addEventListener("click", () => void loadSelectedLog());
  refreshBacktestsBtn?.addEventListener("click", () => void loadBacktestRuns());

  runBacktestForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const out = document.querySelector<HTMLDivElement>("#backtestRunOutput");
    if (!out || !runBacktestForm) return;

    const fd = new FormData(runBacktestForm);
    const payload = {
      account: String(fd.get("account") ?? "").trim(),
      tickersFile: String(fd.get("tickersFile") ?? "trading/trade_universe.txt").trim(),
      universeHistoryDir: parseOptStr(String(fd.get("universeHistoryDir") ?? "")),
      start: parseOptStr(String(fd.get("start") ?? "")),
      end: parseOptStr(String(fd.get("end") ?? "")),
      lookbackMonths: parseOptInt(String(fd.get("lookbackMonths") ?? "")),
      slippageBps: Number(fd.get("slippageBps") ?? 5),
      fee: Number(fd.get("fee") ?? 0),
      runName: parseOptStr(String(fd.get("runName") ?? "")),
      allowApproximateLeaps: fd.get("allowApproximateLeaps") !== null,
    };

    const validationError = validateDateInputs(payload.start, payload.lookbackMonths);
    if (validationError) {
      out.innerHTML = `<div class="down">${esc(validationError)}</div>`;
      return;
    }

    out.innerHTML = `<div class="empty">Running backtest...</div>`;
    try {
      const result = await postJson<BacktestRunResult>("/api/backtests/run", payload);
      out.innerHTML = renderBacktestRunResult(result);
      await loadBacktestRuns();
      await loadBacktestReport(result.runId);
    } catch (error) {
      out.innerHTML = `<div class="down">${esc(error instanceof Error ? error.message : String(error))}</div>`;
    }
  });

  runWalkForwardForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const out = document.querySelector<HTMLDivElement>("#walkForwardOutput");
    if (!out || !runWalkForwardForm) return;

    const fd = new FormData(runWalkForwardForm);
    const payload = {
      account: String(fd.get("account") ?? "").trim(),
      tickersFile: String(fd.get("tickersFile") ?? "trading/trade_universe.txt").trim(),
      universeHistoryDir: parseOptStr(String(fd.get("universeHistoryDir") ?? "")),
      start: parseOptStr(String(fd.get("start") ?? "")),
      end: parseOptStr(String(fd.get("end") ?? "")),
      lookbackMonths: parseOptInt(String(fd.get("lookbackMonths") ?? "")),
      testMonths: Number(fd.get("testMonths") ?? 1),
      stepMonths: Number(fd.get("stepMonths") ?? 1),
      slippageBps: Number(fd.get("slippageBps") ?? 5),
      fee: Number(fd.get("fee") ?? 0),
      runNamePrefix: parseOptStr(String(fd.get("runNamePrefix") ?? "")),
      allowApproximateLeaps: fd.get("allowApproximateLeaps") !== null,
    };

    const validationError = validateDateInputs(payload.start, payload.lookbackMonths);
    if (validationError) {
      out.innerHTML = `<div class="down">${esc(validationError)}</div>`;
      return;
    }

    out.innerHTML = `<div class="empty">Running walk-forward windows...</div>`;
    try {
      const result = await postJson<WalkForwardResult>("/api/backtests/walk-forward", payload);
      out.innerHTML = renderWalkForwardResult(result);
      await loadBacktestRuns();
      if (result.runIds.length) {
        await loadBacktestReport(result.runIds[0]);
      }
    } catch (error) {
      out.innerHTML = `<div class="down">${esc(error instanceof Error ? error.message : String(error))}</div>`;
    }
  });

  backtestAccountSelect?.addEventListener("change", () => {
    applyBacktestAccountDefaults(runBacktestForm, backtestAccountSelect.value);
  });

  walkForwardAccountSelect?.addEventListener("change", () => {
    applyBacktestAccountDefaults(runWalkForwardForm, walkForwardAccountSelect.value);
  });
}

async function bootstrap(): Promise<void> {
  renderShell();
  populateBacktestAccountSelects(cachedAccounts);
  await wireActions();
  await loadAccounts();
  await loadLogFiles();
  await loadBacktestRuns();
}

void bootstrap();
