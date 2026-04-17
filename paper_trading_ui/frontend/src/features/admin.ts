import { renderOperationsOverview, renderPromotionOverview } from "../components/admin-ops";
import { find } from "../lib/dom";
import { currency, esc, pct } from "../lib/format";
import { applyAccountConfigOptionsToAdminForm, getAccountConfigOptions } from "../lib/account-config-options";
import { errorMessage, getJson, postJson } from "../lib/http";
import { numOrUndefined, intOrUndefined, strOrUndefined } from "../lib/form-parse";
import { TEST_ACCOUNT_NAME } from "../lib/constants";
import type {
  AccountListItem,
  AccountSummary,
  AdminCreateAccountPayload,
  OperationsOverviewResponse,
  PromotionOverviewResponse,
} from "../types";

interface DeleteResponse {
  status: string;
  deleted: {
    accounts: number;
    trades: number;
    equitySnapshots: number;
    backtestRuns: number;
    backtestTrades: number;
    backtestEquitySnapshots: number;
  };
}

interface CreateResponse {
  status: string;
  account: AccountSummary;
}

interface CsvExportFile {
  name: string;
  sizeBytes: number;
}

interface CsvExportBatch {
  name: string;
  modifiedAt: string;
  files: CsvExportFile[];
}

interface CsvExportListResponse {
  exports: CsvExportBatch[];
}

interface CsvPreviewResponse {
  exportName: string;
  fileName: string;
  header: string[];
  rows: string[][];
  returned: number;
  truncated: boolean;
}

export interface AdminFeatureOptions {
  onAccountsChanged?: () => Promise<void> | void;
}

export interface AdminFeature {
  wireActions: () => void;
  loadDeleteAccounts: () => Promise<void>;
}

type AdminSection = "jobs" | "accounts" | "test-account" | "promotions" | "artifacts";

function setHtml(target: HTMLElement, className: string, html: string): void {
  target.className = className;
  target.innerHTML = html;
}

function setOutput(
  target: HTMLElement,
  state: "empty" | "error" | "success",
  message: string,
  asHtml: boolean = false,
): void {
  target.className = state;
  if (asHtml) {
    target.innerHTML = message;
  } else {
    target.textContent = message;
  }
}

function isTradeSide(value: string): value is "buy" | "sell" {
  return value === "buy" || value === "sell";
}

function csvListOrUndefined(value: FormDataEntryValue | null): string[] | undefined {
  const raw = strOrUndefined(value);
  if (!raw) return undefined;
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function createAdminFeature(options: AdminFeatureOptions = {}): AdminFeature {
  let cachedCsvExports: CsvExportBatch[] = [];
  let activeAdminSection: AdminSection = "jobs";

  function syncInstrumentDetails(form?: HTMLFormElement | null): void {
    const instrumentMode = form?.elements.namedItem("instrumentMode") as HTMLSelectElement | null;
    const instrumentDetails = find<HTMLDetailsElement>("#adminInstrumentAdvanced");
    if (!instrumentMode || !instrumentDetails) return;

    const isLeaps = instrumentMode.value === "leaps";
    instrumentDetails.open = isLeaps;
  }

  function syncRotationDetails(form?: HTMLFormElement | null): void {
    const rotationEnabled = form?.elements.namedItem("rotationEnabled") as HTMLInputElement | null;
    const rotationDetails = find<HTMLDetailsElement>("#adminRotationDetails");
    if (!rotationEnabled || !rotationDetails) return;

    rotationDetails.open = rotationEnabled.checked;
  }

  function setActiveAdminSection(section: AdminSection): void {
    activeAdminSection = section;
    const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>("[data-admin-section-target]"));
    const panels = Array.from(document.querySelectorAll<HTMLElement>("[data-admin-section-panel]"));
    for (const button of buttons) {
      button.classList.toggle("active", button.dataset.adminSectionTarget === section);
    }
    for (const panel of panels) {
      panel.hidden = panel.dataset.adminSectionPanel !== section;
    }
  }

  function _selectedCsvBatch(): CsvExportBatch | undefined {
    const exportSelect = find<HTMLSelectElement>("#csvExportSelect");
    if (!exportSelect?.value) return undefined;
    return cachedCsvExports.find((item) => item.name === exportSelect.value);
  }

  function renderCsvPreview(data: CsvPreviewResponse): void {
    const output = find<HTMLDivElement>("#csvPreviewOutput");
    const meta = find<HTMLDivElement>("#csvPreviewMeta");
    if (!output || !meta) return;

    const colCount = Math.max(
      data.header.length,
      ...data.rows.map((row) => row.length),
      1,
    );
    const headers = data.header.length
      ? data.header
      : Array.from({ length: colCount }, (_, idx) => `col_${idx + 1}`);

    const headHtml = headers
      .map((h) => `<th>${esc(h)}</th>`)
      .join("");
    const bodyHtml = data.rows
      .map((row) => {
        const cells = Array.from({ length: colCount }, (_, idx) => esc(row[idx] ?? ""));
        return `<tr>${cells.map((cell) => `<td>${cell}</td>`).join("")}</tr>`;
      })
      .join("");

    output.innerHTML = `
      <table class="compare-table admin-csv-table">
        <thead><tr>${headHtml}</tr></thead>
        <tbody>${bodyHtml || `<tr><td colspan="${colCount}">No rows available.</td></tr>`}</tbody>
      </table>
    `;

    meta.textContent = `${data.exportName} / ${data.fileName} - ${data.returned} row(s) shown${data.truncated ? " (truncated)" : ""}.`;
  }

  function syncCsvFileSelect(): void {
    const fileSelect = find<HTMLSelectElement>("#csvFileSelect");
    const output = find<HTMLDivElement>("#csvPreviewOutput");
    const meta = find<HTMLDivElement>("#csvPreviewMeta");
    if (!fileSelect) return;

    const selectedBatch = _selectedCsvBatch();
    if (!selectedBatch) {
      fileSelect.innerHTML = `<option value="">Select CSV file</option>`;
      if (output) output.innerHTML = `<div class="empty">Choose an export and CSV file to preview.</div>`;
      if (meta) meta.textContent = "No CSV loaded yet.";
      return;
    }

    const optionsHtml = selectedBatch.files
      .map((f) => `<option value="${esc(f.name)}">${esc(f.name)}</option>`)
      .join("");
    fileSelect.innerHTML = `<option value="">Select CSV file</option>${optionsHtml}`;

    if (output) output.innerHTML = `<div class="empty">Select a CSV file and click Load Preview.</div>`;
    if (meta) meta.textContent = `${selectedBatch.name} selected. Pick a file to preview.`;
  }

  async function onTestTradeSubmit(event: Event): Promise<void> {
    event.preventDefault();
    const form = event.currentTarget as HTMLFormElement;
    const resultEl = find<HTMLDivElement>("#test-account-trade-result");

    const data = new FormData(form);
    const ticker = ((data.get("ticker") as string | null) ?? "").trim().toUpperCase();
    const sideRaw = ((data.get("side") as string | null) ?? "").trim();
    const qtyRaw = parseFloat((data.get("qty") as string | null) ?? "");
    const priceRaw = parseFloat((data.get("price") as string | null) ?? "");
    const feeRaw = parseFloat((data.get("fee") as string | null) ?? "0");

    if (!ticker || !isTradeSide(sideRaw) || !Number.isFinite(qtyRaw) || !Number.isFinite(priceRaw)) {
      if (resultEl) {
        resultEl.className = "error";
        resultEl.textContent = "Please fill in all required fields correctly.";
      }
      return;
    }

    const payload = {
      ticker,
      side: sideRaw,
      qty: qtyRaw,
      price: priceRaw,
      fee: Number.isFinite(feeRaw) ? feeRaw : 0,
    };

    if (resultEl) {
      resultEl.className = "";
      resultEl.textContent = "Saving\u2026";
    }

    try {
      await postJson<{ status: string }>(
        `/api/accounts/${encodeURIComponent(TEST_ACCOUNT_NAME)}/trades`,
        payload,
      );
      if (resultEl) {
        resultEl.className = "success";
        resultEl.textContent = `Saved: ${payload.side.toUpperCase()} ${payload.qty} \u00d7 ${esc(payload.ticker)} @ $${payload.price.toFixed(2)}`;
      }
      form.reset();
    } catch (err) {
      if (resultEl) {
        resultEl.className = "error";
        resultEl.textContent = errorMessage(err, "Trade failed.");
      }
    }
  }

  async function loadCsvExports(): Promise<void> {
    const exportSelect = find<HTMLSelectElement>("#csvExportSelect");
    const fileSelect = find<HTMLSelectElement>("#csvFileSelect");
    const output = find<HTMLDivElement>("#csvPreviewOutput");
    const meta = find<HTMLDivElement>("#csvPreviewMeta");
    if (!exportSelect || !fileSelect || !output || !meta) return;

    const data = await getJson<CsvExportListResponse>("/api/admin/exports/csv");
    cachedCsvExports = data.exports;

    if (!cachedCsvExports.length) {
      exportSelect.innerHTML = `<option value="">No export batches found</option>`;
      fileSelect.innerHTML = `<option value="">No CSV files found</option>`;
      output.innerHTML = `<div class="empty">No exports available in local/exports yet.</div>`;
      meta.textContent = "Run python scripts/data_ops/export_db_csv.py or python scripts/data_ops/export_db_csv_zip.py to generate db_csv_* database table snapshots first.";
      return;
    }

    const exportOptions = cachedCsvExports
      .map((item) => `<option value="${esc(item.name)}">${esc(item.name)}</option>`)
      .join("");
    exportSelect.innerHTML = `<option value="">Select export batch</option>${exportOptions}`;
    exportSelect.value = cachedCsvExports[0].name;
    syncCsvFileSelect();
  }

  async function loadCsvPreview(): Promise<void> {
    const exportSelect = find<HTMLSelectElement>("#csvExportSelect");
    const fileSelect = find<HTMLSelectElement>("#csvFileSelect");
    const meta = find<HTMLDivElement>("#csvPreviewMeta");
    if (!exportSelect || !fileSelect || !meta) return;

    const exportName = exportSelect.value;
    const fileName = fileSelect.value;
    if (!exportName || !fileName) {
      meta.textContent = "Select both export batch and CSV file first.";
      return;
    }

    meta.textContent = "Loading CSV preview...";
    const q = new URLSearchParams({
      exportName,
      fileName,
      limit: "250",
    });
    const data = await getJson<CsvPreviewResponse>(`/api/admin/exports/csv/preview?${q.toString()}`);
    renderCsvPreview(data);
  }

  async function loadDeleteAccounts(): Promise<void> {
    const deleteSelect = find<HTMLSelectElement>("#deleteAccountSelect");
    const promotionSelect = find<HTMLSelectElement>("#promotionAccountSelect");
    if (!deleteSelect && !promotionSelect) return;

    const data = await getJson<{ accounts: AccountListItem[] }>("/api/accounts");
    const managedAccounts = data.accounts.filter((a) => a.name !== TEST_ACCOUNT_NAME);
    const optionsHtml = managedAccounts
      .map((a) => `<option value="${esc(a.name)}">${esc(a.name)} (${esc(a.strategy)})</option>`)
      .join("");

    if (deleteSelect) {
      deleteSelect.innerHTML = `<option value="">Select account</option>${optionsHtml}`;
    }

    if (promotionSelect) {
      const priorValue = promotionSelect.value;
      promotionSelect.innerHTML = `<option value="">Select account</option>${optionsHtml}`;
      const nextValue = managedAccounts.some((account) => account.name === priorValue) ? priorValue : managedAccounts[0]?.name ?? "";
      promotionSelect.value = nextValue;
      if (nextValue) {
        await loadPromotionOverview();
      } else {
        const output = find<HTMLDivElement>("#promotionOverviewOutput");
        if (output) {
          setOutput(output, "empty", "Create a managed account first to inspect promotion readiness.");
        }
      }
    }
  }

  async function loadOperationsOverview(): Promise<void> {
    const output = find<HTMLDivElement>("#adminOpsOutput");
    const meta = find<HTMLDivElement>("#adminOpsMeta");
    if (!output || !meta) return;

    meta.textContent = "Loading runtime status...";
    try {
      const data = await getJson<OperationsOverviewResponse>("/api/admin/operations/overview");
      setHtml(output, "admin-ops-output", renderOperationsOverview(data));
      meta.textContent =
        `${data.jobs.length} jobs tracked · ` +
        `${data.scheduledRefreshArtifacts.length} refresh artifacts · ` +
        `${data.dailySnapshotArtifacts.length} snapshot artifacts · ` +
        `${data.databaseBackups.length} DB backups.`;
    } catch (error) {
      setOutput(output, "error", errorMessage(error, "Failed to load operations overview."));
      meta.textContent = "Operations overview unavailable.";
    }
  }

  async function loadPromotionOverview(): Promise<void> {
    const accountSelect = find<HTMLSelectElement>("#promotionAccountSelect");
    const strategyInput = find<HTMLInputElement>("#promotionStrategyInput");
    const output = find<HTMLDivElement>("#promotionOverviewOutput");
    if (!accountSelect || !output) return;

    if (!accountSelect.value) {
      setOutput(output, "empty", "Select an account to inspect promotion readiness.");
      return;
    }

    setOutput(output, "empty", "Loading promotion status...");
    try {
      const query = new URLSearchParams({ accountName: accountSelect.value, limit: "5" });
      const strategyName = strategyInput?.value.trim() ?? "";
      if (strategyName) {
        query.set("strategyName", strategyName);
      }
      const data = await getJson<PromotionOverviewResponse>(`/api/admin/promotion/overview?${query.toString()}`);
      setHtml(output, "promotion-output", renderPromotionOverview(data));
    } catch (error) {
      setOutput(output, "error", errorMessage(error, "Failed to load promotion readiness."));
    }
  }

  async function onDeleteSubmit(event: Event): Promise<void> {
    event.preventDefault();
    const form = event.currentTarget as HTMLFormElement;
    const output = find<HTMLDivElement>("#deleteAccountOutput");
    if (!output) return;

    const data = new FormData(form);
    const accountName = strOrUndefined(data.get("accountName"));
    if (!accountName) {
      setOutput(output, "error", "Select an account first.");
      return;
    }

    const confirmed = window.confirm(
      `Delete account '${accountName}' and all related trades/backtests? This cannot be undone.`,
    );
    if (!confirmed) {
      setOutput(output, "empty", "Deletion cancelled.");
      return;
    }

    setOutput(output, "empty", "Deleting account...");

    try {
      const result = await postJson<DeleteResponse>("/api/admin/accounts/delete", {
        accountName,
        confirm: true,
      });
      setOutput(
        output,
        "success",
        `Deleted ${result.deleted.accounts} account.<br>` +
        `Removed ${result.deleted.trades} trades, ${result.deleted.equitySnapshots} snapshots, ` +
        `${result.deleted.backtestRuns} backtest runs.`,
        true,
      );
      await loadDeleteAccounts();
      await loadOperationsOverview();
      await options.onAccountsChanged?.();
    } catch (error) {
      setOutput(output, "error", error instanceof Error ? error.message : "Delete failed.");
    }
  }

  async function onCreateSubmit(event: Event): Promise<void> {
    event.preventDefault();
    const form = event.currentTarget as HTMLFormElement;
    const output = find<HTMLDivElement>("#createAccountOutput");
    if (!output) return;

    const configOptions = getAccountConfigOptions();
    if (!configOptions) {
      setOutput(output, "error", "Account config options are unavailable.");
      return;
    }

    const data = new FormData(form);
    const rotationSchedule = csvListOrUndefined(data.get("rotationScheduleCsv")) ?? [];
    const rotationOverlayWatchlist = csvListOrUndefined(data.get("rotationOverlayWatchlistCsv"));

    const payload: AdminCreateAccountPayload = {
      name: strOrUndefined(data.get("name")),
      descriptiveName: strOrUndefined(data.get("descriptiveName")),
      strategy: strOrUndefined(data.get("strategy")),
      benchmarkTicker: strOrUndefined(data.get("benchmarkTicker")) ?? "SPY",
      initialCash: numOrUndefined(data.get("initialCash")),
      goalMinReturnPct: numOrUndefined(data.get("goalMinReturnPct")),
      goalMaxReturnPct: numOrUndefined(data.get("goalMaxReturnPct")),
      goalPeriod: strOrUndefined(data.get("goalPeriod")) ?? configOptions.defaults.goalPeriod,
      learningEnabled: data.get("learningEnabled") === "on",
      riskPolicy: strOrUndefined(data.get("riskPolicy")) ?? configOptions.defaults.riskPolicy,
      stopLossPct: numOrUndefined(data.get("stopLossPct")),
      takeProfitPct: numOrUndefined(data.get("takeProfitPct")),
      instrumentMode: strOrUndefined(data.get("instrumentMode")) ?? configOptions.defaults.instrumentMode,
      optionStrikeOffsetPct: numOrUndefined(data.get("optionStrikeOffsetPct")),
      optionMinDte: intOrUndefined(data.get("optionMinDte")),
      optionMaxDte: intOrUndefined(data.get("optionMaxDte")),
      optionType: strOrUndefined(data.get("optionType")),
      targetDeltaMin: numOrUndefined(data.get("targetDeltaMin")),
      targetDeltaMax: numOrUndefined(data.get("targetDeltaMax")),
      maxPremiumPerTrade: numOrUndefined(data.get("maxPremiumPerTrade")),
      maxContractsPerTrade: intOrUndefined(data.get("maxContractsPerTrade")),
      ivRankMin: numOrUndefined(data.get("ivRankMin")),
      ivRankMax: numOrUndefined(data.get("ivRankMax")),
      rollDteThreshold: intOrUndefined(data.get("rollDteThreshold")),
      profitTakePct: numOrUndefined(data.get("profitTakePct")),
      maxLossPct: numOrUndefined(data.get("maxLossPct")),
      rotationEnabled: data.get("rotationEnabled") === "on",
      rotationMode: strOrUndefined(data.get("rotationMode")) ?? configOptions.defaults.rotationMode,
      rotationOptimalityMode:
        strOrUndefined(data.get("rotationOptimalityMode")) ?? configOptions.defaults.rotationOptimalityMode,
      rotationIntervalDays: intOrUndefined(data.get("rotationIntervalDays")),
      rotationIntervalMinutes: intOrUndefined(data.get("rotationIntervalMinutes")),
      rotationLookbackDays: intOrUndefined(data.get("rotationLookbackDays")),
      rotationSchedule,
      rotationRegimeStrategyRiskOn: strOrUndefined(data.get("rotationRegimeStrategyRiskOn")),
      rotationRegimeStrategyNeutral: strOrUndefined(data.get("rotationRegimeStrategyNeutral")),
      rotationRegimeStrategyRiskOff: strOrUndefined(data.get("rotationRegimeStrategyRiskOff")),
      rotationOverlayMode:
        strOrUndefined(data.get("rotationOverlayMode")) ?? configOptions.defaults.rotationOverlayMode,
      rotationOverlayMinTickers: intOrUndefined(data.get("rotationOverlayMinTickers")),
      rotationOverlayConfidenceThreshold: numOrUndefined(data.get("rotationOverlayConfidenceThreshold")),
      rotationOverlayWatchlist,
      rotationActiveIndex: intOrUndefined(data.get("rotationActiveIndex")) ?? 0,
      rotationLastAt: strOrUndefined(data.get("rotationLastAt")),
      rotationActiveStrategy: strOrUndefined(data.get("rotationActiveStrategy")),
    };

    if (!payload.name || !payload.strategy || payload.initialCash === undefined) {
      setOutput(output, "error", "Name, strategy, and initial cash are required.");
      return;
    }

    setOutput(output, "empty", "Creating account...");

    try {
      const result = await postJson<CreateResponse>("/api/admin/accounts/create", payload);
      setOutput(
        output,
        "success",
        `Created account ${esc(result.account.name)}.<br>` +
        `Equity: ${currency.format(result.account.equity)} | Return: ${pct(result.account.totalChangePct)}`,
        true,
      );
      form.reset();
      syncInstrumentDetails(form);
      syncRotationDetails(form);
      await loadDeleteAccounts();
      await loadOperationsOverview();
      await options.onAccountsChanged?.();
    } catch (error) {
      setOutput(output, "error", error instanceof Error ? error.message : "Create failed.");
    }
  }

  function wireActions(): void {
    const deleteForm = find<HTMLFormElement>("#deleteAccountForm");
    const createForm = find<HTMLFormElement>("#createAccountForm");
    const instrumentMode = find<HTMLSelectElement>("#adminInstrumentMode");
    const rotationEnabled = createForm?.elements.namedItem("rotationEnabled") as HTMLInputElement | null;
    const exportSelect = find<HTMLSelectElement>("#csvExportSelect");
    const loadPreviewBtn = find<HTMLButtonElement>("#csvPreviewLoadBtn");
    const refreshBtn = find<HTMLButtonElement>("#csvRefreshBtn");
    const opsRefreshBtn = find<HTMLButtonElement>("#adminOpsRefreshBtn");
    const promotionLoadBtn = find<HTMLButtonElement>("#promotionLoadBtn");
    const promotionAccountSelect = find<HTMLSelectElement>("#promotionAccountSelect");
    const promotionStrategyInput = find<HTMLInputElement>("#promotionStrategyInput");
    const adminSectionButtons = Array.from(document.querySelectorAll<HTMLButtonElement>("[data-admin-section-target]"));

    deleteForm?.addEventListener("submit", (event) => {
      void onDeleteSubmit(event);
    });
    createForm?.addEventListener("submit", (event) => {
      void onCreateSubmit(event);
    });

    instrumentMode?.addEventListener("change", () => {
      syncInstrumentDetails(createForm);
    });

    rotationEnabled?.addEventListener("change", () => {
      syncRotationDetails(createForm);
    });

    exportSelect?.addEventListener("change", () => {
      syncCsvFileSelect();
    });

    loadPreviewBtn?.addEventListener("click", () => {
      void loadCsvPreview();
    });

    refreshBtn?.addEventListener("click", () => {
      void loadCsvExports();
    });

    opsRefreshBtn?.addEventListener("click", () => {
      void loadOperationsOverview();
    });

    promotionLoadBtn?.addEventListener("click", () => {
      void loadPromotionOverview();
    });

    promotionAccountSelect?.addEventListener("change", () => {
      void loadPromotionOverview();
    });

    promotionStrategyInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        void loadPromotionOverview();
      }
    });

    for (const button of adminSectionButtons) {
      button.addEventListener("click", () => {
        const section = button.dataset.adminSectionTarget as AdminSection | undefined;
        if (!section) return;
        setActiveAdminSection(section);
      });
    }

    const testTradeForm = find<HTMLFormElement>("#test-account-trade-form");
    testTradeForm?.addEventListener("submit", (event) => {
      void onTestTradeSubmit(event);
    });

    setActiveAdminSection(activeAdminSection);
    syncInstrumentDetails(createForm);
    syncRotationDetails(createForm);
    applyAccountConfigOptionsToAdminForm();
    void loadCsvExports();
    void loadOperationsOverview();
  }

  return {
    wireActions,
    loadDeleteAccounts,
  };
}
