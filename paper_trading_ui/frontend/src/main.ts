import "./styles.css";
import { getJson, postJson } from "./lib/http";
import { renderLogLines } from "./lib/logs";
import { esc } from "./lib/format";
import { find, findAll } from "./lib/dom";
import { accountCard } from "./templates/accounts";
import { renderDetail } from "./templates/detail";
import {
  renderBacktestRunCard,
  renderBacktestReport,
  renderBacktestRunResult,
  renderWalkForwardResult,
  warningListHtml,
} from "./templates/backtesting";
import shellTemplate from "./templates/shell.html?raw";
import type {
  AccountDetail,
  AccountSummary,
  BacktestReport,
  BacktestRunResult,
  BacktestRunSummary,
  WalkForwardResult,
} from "./types";

let cachedAccounts: AccountSummary[] = [];

const appRoot = find<HTMLDivElement>("#app");
if (!appRoot) {
  throw new Error("Missing #app root");
}


function renderShell(): void {
  appRoot.innerHTML = shellTemplate;
}

function populateBacktestAccountSelects(accounts: AccountSummary[]): void {
  const accountOptions = accounts
    .map((a) => `<option value="${esc(a.name)}">${esc(a.displayName)} (${esc(a.name)})</option>`)
    .join("");

  for (const selectId of ["#backtestAccountSelect", "#walkForwardAccountSelect"]) {
    const select = find<HTMLSelectElement>(selectId);
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

  const leapsCheckbox = find<HTMLInputElement>('input[name="allowApproximateLeaps"]', form);
  if (!leapsCheckbox) return;
  leapsCheckbox.checked = account.instrumentMode === "leaps";
}

async function loadAccounts(): Promise<void> {
  const target = find<HTMLDivElement>("#accountsGrid");
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

  for (const btn of findAll<HTMLButtonElement>(".account-card")) {
    btn.addEventListener("click", async () => {
      const accountName = btn.dataset.account;
      if (!accountName) return;
      await loadAccountDetail(accountName);
    });
  }
}

async function loadAccountDetail(accountName: string): Promise<void> {
  const target = find<HTMLDivElement>("#accountDetail");
  if (!target) return;

  target.innerHTML = `<div class="empty">Loading ${esc(accountName)}...</div>`;
  const detail = await getJson<AccountDetail>(`/api/accounts/${encodeURIComponent(accountName)}`);
  target.innerHTML = renderDetail(detail);

  const snapBtn = find<HTMLButtonElement>("#snapshotOneBtn");
  if (snapBtn) {
    snapBtn.addEventListener("click", async () => {
      const acct = snapBtn.dataset.account;
      if (!acct) return;
      await postJson(`/api/actions/snapshot/${encodeURIComponent(acct)}`);
      await loadAccountDetail(acct);
      await loadAccounts();
    });
  }

  const openReportBtn = find<HTMLButtonElement>("#openLatestBacktestReportBtn");
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
  const select = find<HTMLSelectElement>("#logFileSelect");
  if (!select) return;

  const data = await getJson<{ files: string[] }>("/api/logs/files");
  if (!data.files.length) {
    select.innerHTML = `<option value="">No log files</option>`;
    return;
  }

  select.innerHTML = data.files.map((f) => `<option value="${esc(f)}">${esc(f)}</option>`).join("");
}

async function loadSelectedLog(): Promise<void> {
  const select = find<HTMLSelectElement>("#logFileSelect");
  const filterInput = find<HTMLInputElement>("#logFilterInput");
  const output = find<HTMLElement>("#logOutput");
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

function debounce<T extends (...args: never[]) => void>(fn: T, delayMs: number): (...args: Parameters<T>) => void {
  let timer: number | null = null;
  return (...args: Parameters<T>) => {
    if (timer !== null) {
      window.clearTimeout(timer);
    }
    timer = window.setTimeout(() => {
      fn(...args);
    }, delayMs);
  };
}

async function loadBacktestRuns(): Promise<void> {
  const target = find<HTMLDivElement>("#backtestRunsList");
  if (!target) return;

  target.innerHTML = `<div class="empty">Loading backtest runs...</div>`;
  const data = await getJson<{ runs: BacktestRunSummary[] }>("/api/backtests/runs?limit=100");

  if (!data.runs.length) {
    target.innerHTML = `<div class="empty">No backtest runs found yet.</div>`;
    return;
  }

  target.innerHTML = data.runs.map(renderBacktestRunCard).join("");

  for (const btn of findAll<HTMLButtonElement>(".bt-run-item")) {
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
  const target = find<HTMLDivElement>("#backtestReportView");
  if (!target) return;

  target.innerHTML = `<div class="empty">Loading report for run ${runId}...</div>`;
  const report = await getJson<BacktestReport>(`/api/backtests/runs/${runId}`);
  target.innerHTML = renderBacktestReport(report);
}

async function refreshPreflightWarnings(form: HTMLFormElement, outputSelector: string): Promise<void> {
  const target = find<HTMLDivElement>(outputSelector);
  if (!target) return;

  const fd = new FormData(form);
  const account = String(fd.get("account") ?? "").trim();
  if (!account) {
    target.innerHTML = `<div class="empty">Select an account to preview financial-model warnings.</div>`;
    return;
  }

  const payload = {
    account,
    tickersFile: String(fd.get("tickersFile") ?? "trading/trade_universe.txt").trim(),
    universeHistoryDir: parseOptStr(String(fd.get("universeHistoryDir") ?? "")),
    start: parseOptStr(String(fd.get("start") ?? "")),
    end: parseOptStr(String(fd.get("end") ?? "")),
    lookbackMonths: parseOptInt(String(fd.get("lookbackMonths") ?? "")),
    allowApproximateLeaps: fd.get("allowApproximateLeaps") !== null,
  };

  const validationError = validateDateInputs(payload.start, payload.lookbackMonths);
  if (validationError) {
    target.innerHTML = `<div class="down">${esc(validationError)}</div>`;
    return;
  }

  target.innerHTML = `<div class="empty">Checking warnings...</div>`;
  try {
    const result = await postJson<{ warnings: string[] }>("/api/backtests/preflight", payload);
    target.innerHTML = warningListHtml(result.warnings);
  } catch (error) {
    target.innerHTML = `<div class="down">${esc(error instanceof Error ? error.message : String(error))}</div>`;
  }
}

async function wireActions(): Promise<void> {
  const refreshBtn = find<HTMLButtonElement>("#refreshAccountsBtn");
  const snapshotAllBtn = find<HTMLButtonElement>("#snapshotAllBtn");
  const loadLogBtn = find<HTMLButtonElement>("#loadLogBtn");
  const refreshBacktestsBtn = find<HTMLButtonElement>("#refreshBacktestsBtn");
  const runBacktestForm = find<HTMLFormElement>("#runBacktestForm");
  const runWalkForwardForm = find<HTMLFormElement>("#runWalkForwardForm");
  const backtestAccountSelect = find<HTMLSelectElement>("#backtestAccountSelect");
  const walkForwardAccountSelect = find<HTMLSelectElement>("#walkForwardAccountSelect");

  for (const quickButtons of findAll<HTMLDivElement>(".bt-quick-buttons")) {
    quickButtons.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLButtonElement)) return;

      const monthsRaw = target.dataset.lookbackMonths;
      if (!monthsRaw) return;
      const months = Number(monthsRaw);
      if (!Number.isFinite(months) || months <= 0) return;

      const formId = quickButtons.dataset.targetForm;
      if (!formId) return;
      const form = find<HTMLFormElement>(`#${formId}`);
      if (!form) return;

      const lookbackInput = find<HTMLInputElement>('input[name="lookbackMonths"]', form);
      const startInput = find<HTMLInputElement>('input[name="start"]', form);
      const endInput = find<HTMLInputElement>('input[name="end"]', form);
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
    const out = find<HTMLDivElement>("#backtestRunOutput");
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
      await refreshPreflightWarnings(runBacktestForm, "#runBacktestWarnings");
    } catch (error) {
      out.innerHTML = `<div class="down">${esc(error instanceof Error ? error.message : String(error))}</div>`;
    }
  });

  runWalkForwardForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const out = find<HTMLDivElement>("#walkForwardOutput");
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
      await refreshPreflightWarnings(runWalkForwardForm, "#runWalkForwardWarnings");
    } catch (error) {
      out.innerHTML = `<div class="down">${esc(error instanceof Error ? error.message : String(error))}</div>`;
    }
  });

  backtestAccountSelect?.addEventListener("change", () => {
    applyBacktestAccountDefaults(runBacktestForm, backtestAccountSelect.value);
    if (runBacktestForm) {
      void refreshPreflightWarnings(runBacktestForm, "#runBacktestWarnings");
    }
  });

  walkForwardAccountSelect?.addEventListener("change", () => {
    applyBacktestAccountDefaults(runWalkForwardForm, walkForwardAccountSelect.value);
    if (runWalkForwardForm) {
      void refreshPreflightWarnings(runWalkForwardForm, "#runWalkForwardWarnings");
    }
  });

  const preflightWireups: Array<[HTMLFormElement | null, string]> = [
    [runBacktestForm, "#runBacktestWarnings"],
    [runWalkForwardForm, "#runWalkForwardWarnings"],
  ];
  for (const [form, target] of preflightWireups) {
    if (!form) continue;
    const debouncedRefresh = debounce(() => {
      void refreshPreflightWarnings(form, target);
    }, 300);
    const inputs = findAll<HTMLInputElement | HTMLSelectElement>(
      'input[name="tickersFile"], input[name="universeHistoryDir"], input[name="start"], input[name="end"], input[name="lookbackMonths"], input[name="allowApproximateLeaps"], select[name="account"]',
      form,
    );
    for (const input of inputs) {
      input.addEventListener("change", () => {
        void refreshPreflightWarnings(form, target);
      });
      input.addEventListener("input", () => {
        debouncedRefresh();
      });
    }
    void refreshPreflightWarnings(form, target);
  }
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
