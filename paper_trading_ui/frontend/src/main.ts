import "./styles.css";

type AccountSummary = {
  name: string;
  displayName: string;
  strategy: string;
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

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

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

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

async function postJson(path: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
}

function renderShell(): void {
  const root = appRoot;
  root.innerHTML = `
    <div class="scene"></div>
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
        <pre id="logOutput">Select a log file to begin.</pre>
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

async function loadAccounts(): Promise<void> {
  const target = document.querySelector<HTMLDivElement>("#accountsGrid");
  if (!target) return;

  target.innerHTML = `<div class="empty">Loading accounts...</div>`;
  const data = await getJson<{ accounts: AccountSummary[] }>("/api/accounts");

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

  return `
    <div class="detail-head">
      <div>
        <h3>${esc(detail.account.displayName)}</h3>
        <p>${esc(detail.account.name)} | ${esc(detail.account.strategy)} | ${esc(detail.account.benchmark)}</p>
      </div>
      <button id="snapshotOneBtn" data-account="${esc(detail.account.name)}">Snapshot This Account</button>
    </div>

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
  output.textContent = data.lines.join("\n") || "No lines matched this filter.";
}

async function wireActions(): Promise<void> {
  const refreshBtn = document.querySelector<HTMLButtonElement>("#refreshAccountsBtn");
  const snapshotAllBtn = document.querySelector<HTMLButtonElement>("#snapshotAllBtn");
  const loadLogBtn = document.querySelector<HTMLButtonElement>("#loadLogBtn");

  refreshBtn?.addEventListener("click", () => void loadAccounts());

  snapshotAllBtn?.addEventListener("click", async () => {
    await postJson("/api/actions/snapshot-all");
    await loadAccounts();
  });

  loadLogBtn?.addEventListener("click", () => void loadSelectedLog());
}

async function bootstrap(): Promise<void> {
  renderShell();
  await wireActions();
  await loadAccounts();
  await loadLogFiles();
}

void bootstrap();
