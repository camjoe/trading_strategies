import { find, findAll } from "../../lib/dom";
import { esc } from "../../lib/format";
import { errorMessage, getJson, postJson } from "../../lib/http";
import { parseRunId } from "../../lib/parse";
import { debounce } from "../../lib/timing";
import {
  renderBacktestReport,
  renderBacktestRunCard,
  warningListHtml,
} from "../../components/backtesting";
import type { AccountListItem } from "../../types/accounts";
import type { BacktestReport, BacktestRunResult, BacktestRunSummary } from "../../types/backtesting";
import {
  BACKTEST_ACCOUNT_SELECT_SELECTOR,
  BACKTEST_REPORT_VIEW_SELECTOR,
  BACKTEST_RUN_ITEM_SELECTOR,
  BACKTEST_RUNS_LIST_SELECTOR,
  BACKTEST_WARNINGS_SELECTOR,
  PREFLIGHT_INPUT_SELECTOR,
  QUICK_LOOKBACK_BUTTONS_SELECTOR,
  REFRESH_BACKTESTS_BUTTON_SELECTOR,
  RUN_BACKTEST_FORM_SELECTOR,
  renderDownMessage,
} from "./constants";
import {
  buildBacktestBasePayload,
  buildBacktestRunPayload,
  validateDateInputs,
} from "./payloads";
import type { BacktestingFeature } from "./types";

export function createBacktestingFeature(): BacktestingFeature {
  let cachedAccounts: AccountListItem[] = [];

  function populateBacktestAccountSelects(accounts: AccountListItem[]): void {
    const accountOptions = accounts
      .map((account) => `<option value="${esc(account.name)}">${esc(account.displayName)} (${esc(account.name)})</option>`)
      .join("");

    const select = find<HTMLSelectElement>(BACKTEST_ACCOUNT_SELECT_SELECTOR);
    if (!select) return;
    const previous = select.value;
    select.innerHTML = `<option value="">Select account</option>${accountOptions}`;
    if (previous && accounts.some((account) => account.name === previous)) {
      select.value = previous;
    }
  }

  function applyBacktestAccountDefaults(form: HTMLFormElement | null, accountName: string): void {
    if (!form || !accountName) return;
    const account = cachedAccounts.find((item) => item.name === accountName);
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

    for (const button of target.querySelectorAll<HTMLButtonElement>(BACKTEST_RUN_ITEM_SELECTOR)) {
      button.addEventListener("click", () => {
        const runId = parseRunId(button.dataset.runId);
        if (runId === null) return;
        void loadBacktestReportTo(runId, reportTargetSelector);
      });
    }
  }

  async function loadBacktestRuns(): Promise<void> {
    const backtestTarget = find<HTMLDivElement>(BACKTEST_RUNS_LIST_SELECTOR);
    if (!backtestTarget) return;

    backtestTarget.innerHTML = `<div class="empty">Loading backtest runs...</div>`;
    // The API returns standalone runs only, so no client-side split is needed.
    const data = await getJson<{ runs: BacktestRunSummary[] }>("/api/backtests/runs?limit=100");
    renderRunsList(backtestTarget, data.runs, "No backtest runs found yet.", BACKTEST_REPORT_VIEW_SELECTOR);
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
    const runBacktestForm = find<HTMLFormElement>(RUN_BACKTEST_FORM_SELECTOR);
    const backtestAccountSelect = find<HTMLSelectElement>(BACKTEST_ACCOUNT_SELECT_SELECTOR);

    wireQuickLookbackButtons();

    refreshBacktestsBtn?.addEventListener("click", () => {
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

    backtestAccountSelect?.addEventListener("change", () => {
      applyBacktestAccountDefaults(runBacktestForm, backtestAccountSelect.value);
      if (runBacktestForm) {
        void refreshPreflightWarnings(runBacktestForm, BACKTEST_WARNINGS_SELECTOR);
      }
    });

    wirePreflight(runBacktestForm, BACKTEST_WARNINGS_SELECTOR);
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
