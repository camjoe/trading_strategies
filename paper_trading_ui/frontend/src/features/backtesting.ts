import { find, findAll } from "../lib/dom";
import { esc } from "../lib/format";
import { getJson, postJson } from "../lib/http";
import { debounce } from "../lib/timing";
import {
  renderBacktestReport,
  renderBacktestRunCard,
  renderWalkForwardResult,
  warningListHtml,
} from "../components/backtesting";
import type {
  AccountListItem,
  BacktestReport,
  BacktestRunResult,
  BacktestRunSummary,
  WalkForwardResult,
} from "../types";

export interface BacktestingFeature {
  setAccounts: (accounts: AccountListItem[]) => void;
  loadBacktestRuns: () => Promise<void>;
  loadBacktestReport: (runId: number) => Promise<void>;
  wireActions: () => void;
}

const PREFLIGHT_INPUT_SELECTOR =
  'input[name="tickersFile"], input[name="universeHistoryDir"], input[name="start"], input[name="end"], input[name="lookbackMonths"], input[name="allowApproximateLeaps"], select[name="account"]';

const BACKTEST_ACCOUNT_SELECT_SELECTOR = "#backtestAccountSelect";
const WALK_FORWARD_ACCOUNT_SELECT_SELECTOR = "#walkForwardAccountSelect";

const BACKTEST_WARNINGS_SELECTOR = "#runBacktestWarnings";
const WALK_FORWARD_WARNINGS_SELECTOR = "#runWalkForwardWarnings";

const BACKTEST_RUNS_LIST_SELECTOR = "#backtestRunsList";
const BACKTEST_REPORT_VIEW_SELECTOR = "#backtestReportView";
const REFRESH_BACKTESTS_BUTTON_SELECTOR = "#refreshBacktestsBtn";
const WALK_FORWARD_RUNS_LIST_SELECTOR = "#walkForwardRunsList";
const WALK_FORWARD_REPORT_VIEW_SELECTOR = "#walkForwardReportView";
const REFRESH_WALK_FORWARD_BUTTON_SELECTOR = "#refreshWalkForwardBtn";
const RUN_BACKTEST_FORM_SELECTOR = "#runBacktestForm";
const RUN_WALK_FORWARD_FORM_SELECTOR = "#runWalkForwardForm";

const BACKTEST_RUN_ITEM_SELECTOR = ".bt-run-item";
const QUICK_LOOKBACK_BUTTONS_SELECTOR = ".bt-quick-buttons";

interface BacktestBasePayload {
  account: string;
  tickersFile: string;
  universeHistoryDir: string | null;
  start: string | null;
  end: string | null;
  lookbackMonths: number | null;
  allowApproximateLeaps: boolean;
}

interface BacktestRunPayload extends BacktestBasePayload {
  slippageBps: number;
  fee: number;
  runName: string | null;
}

interface WalkForwardPayload extends BacktestBasePayload {
  testMonths: number;
  stepMonths: number;
  slippageBps: number;
  fee: number;
  runNamePrefix: string | null;
}

function parseRunId(raw: string | undefined): number | null {
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function renderDownMessage(message: string): string {
  return `<div class="down">${esc(message)}</div>`;
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

function parseFormNumber(fd: FormData, key: string, fallback: number): number {
  const raw = String(fd.get(key) ?? "").trim();
  if (!raw) {
    return fallback;
  }
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function buildBacktestBasePayload(fd: FormData): BacktestBasePayload {
  return {
    account: String(fd.get("account") ?? "").trim(),
    tickersFile: String(fd.get("tickersFile") ?? "trading/config/trade_universe.txt").trim(),
    universeHistoryDir: parseOptStr(String(fd.get("universeHistoryDir") ?? "")),
    start: parseOptStr(String(fd.get("start") ?? "")),
    end: parseOptStr(String(fd.get("end") ?? "")),
    lookbackMonths: parseOptInt(String(fd.get("lookbackMonths") ?? "")),
    allowApproximateLeaps: fd.get("allowApproximateLeaps") !== null,
  };
}

function buildBacktestRunPayload(form: HTMLFormElement): BacktestRunPayload {
  const fd = new FormData(form);
  return {
    ...buildBacktestBasePayload(fd),
    slippageBps: parseFormNumber(fd, "slippageBps", 5),
    fee: parseFormNumber(fd, "fee", 0),
    runName: parseOptStr(String(fd.get("runName") ?? "")),
  };
}

function buildWalkForwardPayload(form: HTMLFormElement): WalkForwardPayload {
  const fd = new FormData(form);
  return {
    ...buildBacktestBasePayload(fd),
    testMonths: parseFormNumber(fd, "testMonths", 1),
    stepMonths: parseFormNumber(fd, "stepMonths", 1),
    slippageBps: parseFormNumber(fd, "slippageBps", 5),
    fee: parseFormNumber(fd, "fee", 0),
    runNamePrefix: parseOptStr(String(fd.get("runNamePrefix") ?? "")),
  };
}

function validateDateInputs(start: string | null, lookbackMonths: number | null): string | null {
  if (start && lookbackMonths !== null) {
    return "Use either Start date or Lookback months, not both.";
  }
  return null;
}

export function createBacktestingFeature(): BacktestingFeature {
  let cachedAccounts: AccountListItem[] = [];

  const isWalkForwardRun = (run: BacktestRunSummary): boolean =>
    Boolean(run.runName && /^wf(?:_|-)/i.test(run.runName));

  function populateBacktestAccountSelects(accounts: AccountListItem[]): void {
    const accountOptions = accounts
      .map((a) => `<option value="${esc(a.name)}">${esc(a.displayName)} (${esc(a.name)})</option>`)
      .join("");

    for (const selectId of [BACKTEST_ACCOUNT_SELECT_SELECTOR, WALK_FORWARD_ACCOUNT_SELECT_SELECTOR]) {
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

  function renderRunsList(
    target: HTMLDivElement,
    runs: BacktestRunSummary[],
    emptyMessage: string,
    reportTargetSelector: string,
  ): void {
    if (!runs.length) {
      target.innerHTML = `<div class="empty">${esc(emptyMessage)}</div>`;
      return;
    }

    target.innerHTML = runs.map(renderBacktestRunCard).join("");

    for (const btn of target.querySelectorAll<HTMLButtonElement>(BACKTEST_RUN_ITEM_SELECTOR)) {
      btn.addEventListener("click", () => {
        const runId = parseRunId(btn.dataset.runId);
        if (runId === null) return;
        void loadBacktestReportTo(runId, reportTargetSelector);
      });
    }
  }

  async function loadBacktestRuns(): Promise<void> {
    const backtestTarget = find<HTMLDivElement>(BACKTEST_RUNS_LIST_SELECTOR);
    const walkForwardTarget = find<HTMLDivElement>(WALK_FORWARD_RUNS_LIST_SELECTOR);
    if (!backtestTarget || !walkForwardTarget) return;

    backtestTarget.innerHTML = `<div class="empty">Loading backtest runs...</div>`;
    walkForwardTarget.innerHTML = `<div class="empty">Loading walk-forward runs...</div>`;
    const data = await getJson<{ runs: BacktestRunSummary[] }>("/api/backtests/runs?limit=100");

    const backtestRuns = data.runs.filter((run) => !isWalkForwardRun(run));
    const walkForwardRuns = data.runs.filter(isWalkForwardRun);

    renderRunsList(backtestTarget, backtestRuns, "No backtest runs found yet.", BACKTEST_REPORT_VIEW_SELECTOR);
    renderRunsList(
      walkForwardTarget,
      walkForwardRuns,
      "No walk-forward runs found yet.",
      WALK_FORWARD_REPORT_VIEW_SELECTOR,
    );
  }

  async function loadBacktestReportTo(runId: number, reportSelector: string): Promise<void> {
    const target = find<HTMLDivElement>(reportSelector);
    if (!target) return;

    target.innerHTML = `<div class="empty">Loading report for run ${runId}...</div>`;
    const report = await getJson<BacktestReport>(`/api/backtests/runs/${runId}`);
    target.innerHTML = renderBacktestReport(report);
  }

  async function loadBacktestReport(runId: number): Promise<void> {
    await loadBacktestReportTo(runId, BACKTEST_REPORT_VIEW_SELECTOR);
  }

  async function refreshPreflightWarnings(form: HTMLFormElement, outputSelector: string): Promise<void> {
    const target = find<HTMLDivElement>(outputSelector);
    if (!target) return;

    const payload = buildBacktestBasePayload(new FormData(form));
    if (!payload.account) {
      target.innerHTML = `<div class="empty">Select an account to preview financial-model warnings.</div>`;
      return;
    }

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
      target.innerHTML = renderDownMessage(errorMessage(error));
    }
  }

  function wireQuickLookbackButtons(): void {
    for (const quickButtons of findAll<HTMLDivElement>(QUICK_LOOKBACK_BUTTONS_SELECTOR)) {
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
  }

  function wirePreflight(form: HTMLFormElement | null, target: string): void {
    if (!form) return;

    const debouncedRefresh = debounce(() => {
      void refreshPreflightWarnings(form, target);
    }, 300);

    const inputs = findAll<HTMLInputElement | HTMLSelectElement>(
      PREFLIGHT_INPUT_SELECTOR,
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

  function wireActions(): void {
    const refreshBacktestsBtn = find<HTMLButtonElement>(REFRESH_BACKTESTS_BUTTON_SELECTOR);
    const refreshWalkForwardBtn = find<HTMLButtonElement>(REFRESH_WALK_FORWARD_BUTTON_SELECTOR);
    const runBacktestForm = find<HTMLFormElement>(RUN_BACKTEST_FORM_SELECTOR);
    const runWalkForwardForm = find<HTMLFormElement>(RUN_WALK_FORWARD_FORM_SELECTOR);
    const backtestAccountSelect = find<HTMLSelectElement>(BACKTEST_ACCOUNT_SELECT_SELECTOR);
    const walkForwardAccountSelect = find<HTMLSelectElement>(WALK_FORWARD_ACCOUNT_SELECT_SELECTOR);

    wireQuickLookbackButtons();

    refreshBacktestsBtn?.addEventListener("click", () => {
      void loadBacktestRuns();
    });

    refreshWalkForwardBtn?.addEventListener("click", () => {
      void loadBacktestRuns();
    });

    runBacktestForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const reportTarget = find<HTMLDivElement>(BACKTEST_REPORT_VIEW_SELECTOR);
      if (!reportTarget || !runBacktestForm) return;

      const payload = buildBacktestRunPayload(runBacktestForm);

      const validationError = validateDateInputs(payload.start, payload.lookbackMonths);
      if (validationError) {
        reportTarget.innerHTML = renderDownMessage(validationError);
        return;
      }

      reportTarget.innerHTML = `<div class="empty">Running backtest...</div>`;
      try {
        const result = await postJson<BacktestRunResult>("/api/backtests/run", payload);
        await loadBacktestRuns();
        await loadBacktestReport(result.runId);
        await refreshPreflightWarnings(runBacktestForm, BACKTEST_WARNINGS_SELECTOR);
      } catch (error) {
        reportTarget.innerHTML = renderDownMessage(errorMessage(error));
      }
    });

    runWalkForwardForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const reportTarget = find<HTMLDivElement>(WALK_FORWARD_REPORT_VIEW_SELECTOR);
      if (!reportTarget || !runWalkForwardForm) return;

      const payload = buildWalkForwardPayload(runWalkForwardForm);

      const validationError = validateDateInputs(payload.start, payload.lookbackMonths);
      if (validationError) {
        reportTarget.innerHTML = renderDownMessage(validationError);
        return;
      }

      reportTarget.innerHTML = `<div class="empty">Running walk-forward windows...</div>`;
      try {
        const result = await postJson<WalkForwardResult>("/api/backtests/walk-forward", payload);
        await loadBacktestRuns();
        reportTarget.innerHTML = renderWalkForwardResult(result);
        if (result.runIds.length) {
          const latestRunId = result.runIds[result.runIds.length - 1];
          const report = await getJson<BacktestReport>(`/api/backtests/runs/${latestRunId}`);
          reportTarget.innerHTML = `${renderWalkForwardResult(result)}${renderBacktestReport(report)}`;
        }
        await refreshPreflightWarnings(runWalkForwardForm, WALK_FORWARD_WARNINGS_SELECTOR);
      } catch (error) {
        reportTarget.innerHTML = renderDownMessage(errorMessage(error));
      }
    });

    backtestAccountSelect?.addEventListener("change", () => {
      applyBacktestAccountDefaults(runBacktestForm, backtestAccountSelect.value);
      if (runBacktestForm) {
        void refreshPreflightWarnings(runBacktestForm, BACKTEST_WARNINGS_SELECTOR);
      }
    });

    walkForwardAccountSelect?.addEventListener("change", () => {
      applyBacktestAccountDefaults(runWalkForwardForm, walkForwardAccountSelect.value);
      if (runWalkForwardForm) {
        void refreshPreflightWarnings(runWalkForwardForm, WALK_FORWARD_WARNINGS_SELECTOR);
      }
    });

    wirePreflight(runBacktestForm, BACKTEST_WARNINGS_SELECTOR);
    wirePreflight(runWalkForwardForm, WALK_FORWARD_WARNINGS_SELECTOR);
  }

  function setAccounts(accounts: AccountListItem[]): void {
    cachedAccounts = accounts;
    populateBacktestAccountSelects(cachedAccounts);
  }

  return {
    setAccounts,
    loadBacktestRuns,
    loadBacktestReport,
    wireActions,
  };
}
