import { find, findAll } from "../lib/dom";
import { esc } from "../lib/format";
import { errorMessage, getJson, patchJson, postJson } from "../lib/http";
import { parseRunId } from "../lib/parse";
import { TEST_ACCOUNT_NAME } from "../lib/constants";
import { accountCard } from "../components/accounts";
import { renderDetail, renderAnalysisPanel } from "../components/detail";
import type { AccountAnalysis, AccountDetail, AccountListItem, AccountParamsUpdate } from "../types";

export interface AccountsFeatureOptions {
  onAccountsLoaded?: (accounts: AccountListItem[]) => void;
  onOpenRunReport?: (runId: number) => Promise<void> | void;
}

export interface AccountsFeature {
  getAccounts: () => AccountListItem[];
  loadAccounts: () => Promise<void>;
  loadAccountDetail: (accountName: string) => Promise<void>;
  snapshotAll: () => Promise<void>;
  wireActions: () => void;
}

function bindClick<T extends Element>(selector: string, handler: (element: T) => Promise<void> | void): void {
  const element = find<T>(selector);
  if (!element) return;
  element.addEventListener("click", () => {
    void handler(element);
  });
}

export function createAccountsFeature(options: AccountsFeatureOptions = {}): AccountsFeature {
  let cachedAccounts: AccountListItem[] = [];
  let currentDetail: AccountDetail | null = null;
  let currentAccountName: string | null = null;
  let currentTradePage = 1;
  let currentAnalysis: AccountAnalysis | null = null;
  let currentDetailSection: "summary" | "positions" | "trades" | "snapshots" = "summary";
  let accountBrowserOpen = false;
  const tradePageSize = 20;

  function getSelectedAccount(): AccountListItem | null {
    if (!currentAccountName) {
      return null;
    }
    return cachedAccounts.find((account) => account.name === currentAccountName) ?? null;
  }

  function updateAccountBrowserToggle(): void {
    const button = find<HTMLButtonElement>("#toggleAccountBrowserBtn");
    const panel = find<HTMLDivElement>("#accountBrowserPanel");
    if (!button || !panel) {
      return;
    }

    panel.hidden = !accountBrowserOpen;
    button.textContent = accountBrowserOpen ? "Hide Account Browser" : "Browse Accounts";
    button.setAttribute("aria-expanded", String(accountBrowserOpen));
  }

  function renderAccountBrowser(searchTerm: string = ""): void {
    const target = find<HTMLDivElement>("#accountsGrid");
    if (!target) return;

    const normalized = searchTerm.trim().toLowerCase();
    const visibleAccounts = cachedAccounts.filter((account) => {
      if (!normalized) {
        return true;
      }
      return [account.displayName, account.name, account.strategy, account.benchmark]
        .join(" ")
        .toLowerCase()
        .includes(normalized);
    });

    if (!visibleAccounts.length) {
      target.innerHTML = `<div class="empty">No accounts match that search.</div>`;
      return;
    }

    target.innerHTML = visibleAccounts
      .map((account) => accountCard(account, { selected: account.name === currentAccountName }))
      .join("");

    for (const btn of findAll<HTMLButtonElement>(".account-card")) {
      btn.addEventListener("click", async () => {
        const accountName = btn.dataset.account;
        if (!accountName) return;
        accountBrowserOpen = false;
        updateAccountBrowserToggle();
        await loadAccountDetail(accountName);
      });
    }
  }

  function populateAccountSelect(): void {
    const select = find<HTMLSelectElement>("#accountSelect");
    if (!select) return;

    if (!cachedAccounts.length) {
      select.innerHTML = `<option value="">No accounts</option>`;
      return;
    }

    select.innerHTML = cachedAccounts
      .map((account) => `<option value="${esc(account.name)}">${esc(account.displayName)} (${esc(account.name)})</option>`)
      .join("");

    if (currentAccountName) {
      select.value = currentAccountName;
    }
  }

  function renderWorkspaceMeta(): void {
    const meta = find<HTMLParagraphElement>("#accountWorkspaceMeta");
    if (!meta) return;

    const account = getSelectedAccount();
    if (!account) {
      meta.textContent = cachedAccounts.length
        ? "Select an account to focus the workspace."
        : "No accounts found in the paper trading database.";
      return;
    }

    meta.textContent = `${account.displayName} (${account.name}) - ${account.strategy} vs ${account.benchmark}.`;
  }

  function renderCurrentDetail(): void {
    const target = find<HTMLDivElement>("#accountDetail");
    if (!target || !currentDetail) return;

    target.innerHTML = renderDetail(currentDetail, {
      activeSection: currentDetailSection,
      tradePage: currentTradePage,
      tradePageSize,
      showAddTrade: currentDetail.account.name === TEST_ACCOUNT_NAME,
    });

    bindClick<HTMLButtonElement>("#snapshotOneBtn", async (button) => {
      const accountName = button.dataset.account;
      if (!accountName) return;
      await postJson(`/api/actions/snapshot/${encodeURIComponent(accountName)}`);
      await loadAccountDetail(accountName);
      await loadAccounts();
    });

    bindClick<HTMLButtonElement>("#openLatestBacktestReportBtn", async (button) => {
      const runId = parseRunId(button.dataset.runId);
      if (runId === null) return;
      await options.onOpenRunReport?.(runId);
    });

    bindClick<HTMLButtonElement>("#recentTradesPrevBtn", () => {
      currentTradePage = Math.max(1, currentTradePage - 1);
      renderCurrentDetail();
    });

    bindClick<HTMLButtonElement>("#recentTradesNextBtn", () => {
      if (!currentDetail) return;
      const totalPages = Math.max(1, Math.ceil(currentDetail.trades.length / tradePageSize));
      currentTradePage = Math.min(totalPages, currentTradePage + 1);
      renderCurrentDetail();
    });

    bindClick<HTMLButtonElement>("#addTradeBtn", () => {
      const panel = find<HTMLDivElement>("#addTradePanel");
      if (panel) panel.hidden = !panel.hidden;
    });

    bindClick<HTMLButtonElement>("#addTradeCancelBtn", () => {
      const panel = find<HTMLDivElement>("#addTradePanel");
      if (panel) panel.hidden = true;
    });

    bindClick<HTMLButtonElement>("#addTradeSaveBtn", async () => {
      if (!currentDetail) return;
      const accountName = currentDetail.account.name;
      const msgEl = find<HTMLDivElement>("#addTradeMsg");

      const ticker = find<HTMLInputElement>("#addTradeTicker")?.value.trim().toUpperCase();
      const side = find<HTMLSelectElement>("#addTradeSide")?.value;
      const qty = parseFloat(find<HTMLInputElement>("#addTradeQty")?.value ?? "");
      const price = parseFloat(find<HTMLInputElement>("#addTradePrice")?.value ?? "");
      const fee = parseFloat(find<HTMLInputElement>("#addTradeFee")?.value ?? "0");

      if (!ticker || !side || !Number.isFinite(qty) || qty <= 0 || !Number.isFinite(price) || price <= 0) {
        if (msgEl) { msgEl.className = "error"; msgEl.textContent = "Ticker, qty, and price are required."; }
        return;
      }

      try {
        await postJson<{ status: string }>(
          `/api/accounts/${encodeURIComponent(accountName)}/trades`,
          { ticker, side, qty, price, fee: Number.isFinite(fee) ? fee : 0 },
        );
        if (msgEl) { msgEl.className = ""; msgEl.textContent = "Trade added."; }
        setTimeout(() => { void loadAccountDetail(accountName); }, 800);
      } catch (err) {
        if (msgEl) {
          msgEl.className = "error";
          msgEl.textContent = errorMessage(err, "Failed to add trade.");
        }
      }
    });

    bindClick<HTMLButtonElement>("#editParamsBtn", () => {
      const panel = find<HTMLDivElement>("#editParamsPanel");
      if (panel) panel.hidden = !panel.hidden;
    });

    bindClick<HTMLButtonElement>("#editParamsCancelBtn", () => {
      const panel = find<HTMLDivElement>("#editParamsPanel");
      if (panel) panel.hidden = true;
    });

    bindClick<HTMLButtonElement>("#editParamsSaveBtn", async () => {
      if (!currentDetail) return;
      const accountName = currentDetail.account.name;
      const msgEl = find<HTMLDivElement>("#editParamsMsg");

      const readStr = (id: string) => find<HTMLInputElement>(id)?.value.trim() || undefined;
      const readNum = (id: string): number | null | undefined => {
        const v = find<HTMLInputElement>(id)?.value.trim();
        if (v === undefined || v === "") return undefined;
        const n = parseFloat(v);
        return Number.isFinite(n) ? n : undefined;
      };
      const readInt = (id: string): number | null | undefined => {
        const v = find<HTMLInputElement>(id)?.value.trim();
        if (v === undefined || v === "") return undefined;
        const n = parseInt(v, 10);
        return Number.isFinite(n) ? n : undefined;
      };
      const readCsv = (id: string): string[] | undefined => {
        const input = find<HTMLInputElement>(id);
        if (!input) return undefined;
        const value = input.value.trim();
        if (!value) return [];
        return value
          .split(",")
          .map((item) => item.trim())
          .filter((item) => item.length > 0);
      };

      const payload: AccountParamsUpdate = {
        strategy: readStr("#editStrategyInput"),
        descriptiveName: readStr("#editDisplayNameInput"),
        riskPolicy: find<HTMLSelectElement>("#editRiskPolicySelect")?.value || undefined,
        instrumentMode: find<HTMLSelectElement>("#editInstrumentModeSelect")?.value || undefined,
        stopLossPct: readNum("#editStopLossPctInput"),
        takeProfitPct: readNum("#editTakeProfitPctInput"),
        learningEnabled: (() => {
          const el = find<HTMLSelectElement>("#editLearningEnabledSelect");
          return el ? el.value === "true" : undefined;
        })(),
        goalMinReturnPct: readNum("#editGoalMinReturnInput"),
        goalMaxReturnPct: readNum("#editGoalMaxReturnInput"),
        goalPeriod: readStr("#editGoalPeriodInput"),
        optionType: find<HTMLSelectElement>("#editOptionTypeSelect")?.value || undefined,
        optionStrikeOffsetPct: readNum("#editOptionStrikeOffsetInput"),
        optionMinDte: readInt("#editOptionMinDteInput"),
        optionMaxDte: readInt("#editOptionMaxDteInput"),
        targetDeltaMin: readNum("#editTargetDeltaMinInput"),
        targetDeltaMax: readNum("#editTargetDeltaMaxInput"),
        ivRankMin: readNum("#editIvRankMinInput"),
        ivRankMax: readNum("#editIvRankMaxInput"),
        maxPremiumPerTrade: readNum("#editMaxPremiumInput"),
        maxContractsPerTrade: readInt("#editMaxContractsInput"),
        rollDteThreshold: readInt("#editRollDteThresholdInput"),
        profitTakePct: readNum("#editProfitTakePctInput"),
        maxLossPct: readNum("#editMaxLossPctInput"),
        rotationEnabled: (() => {
          const el = find<HTMLSelectElement>("#editRotationEnabledSelect");
          return el ? el.value === "true" : undefined;
        })(),
        rotationMode: find<HTMLSelectElement>("#editRotationModeSelect")?.value || undefined,
        rotationOptimalityMode: find<HTMLSelectElement>("#editRotationOptimalityModeSelect")?.value || undefined,
        rotationIntervalDays: readInt("#editRotationIntervalDaysInput"),
        rotationIntervalMinutes: readInt("#editRotationIntervalMinutesInput"),
        rotationLookbackDays: readInt("#editRotationLookbackDaysInput"),
        rotationSchedule: readCsv("#editRotationScheduleInput"),
        rotationRegimeStrategyRiskOn: readStr("#editRotationRegimeRiskOnInput"),
        rotationRegimeStrategyNeutral: readStr("#editRotationRegimeNeutralInput"),
        rotationRegimeStrategyRiskOff: readStr("#editRotationRegimeRiskOffInput"),
        rotationOverlayMode: find<HTMLSelectElement>("#editRotationOverlayModeSelect")?.value || undefined,
        rotationOverlayMinTickers: readInt("#editRotationOverlayMinTickersInput"),
        rotationOverlayConfidenceThreshold: readNum("#editRotationOverlayConfidenceThresholdInput"),
        rotationOverlayWatchlist: readCsv("#editRotationOverlayWatchlistInput"),
        rotationActiveIndex: readInt("#editRotationActiveIndexInput"),
        rotationLastAt: readStr("#editRotationLastAtInput"),
        rotationActiveStrategy: readStr("#editRotationActiveStrategyInput"),
      };

      try {
        await patchJson<{ status: string }>(
          `/api/accounts/${encodeURIComponent(accountName)}/params`,
          payload,
        );
        if (msgEl) {
          msgEl.className = "";
          msgEl.textContent = "Saved.";
        }
        setTimeout(() => {
          void loadAccountDetail(accountName);
        }, 800);
      } catch (err) {
        if (msgEl) {
          msgEl.className = "error";
          msgEl.textContent = errorMessage(err, "Save failed.");
        }
      }
    });

    // Re-apply cached analysis so pagination doesn't wipe it back to "Loading…"
    if (currentAnalysis) {
      const panel = find<HTMLElement>("#analysisPanel");
      if (panel) panel.innerHTML = renderAnalysisPanel(currentAnalysis);
    }

    for (const button of findAll<HTMLButtonElement>(".detail-section-tab")) {
      button.addEventListener("click", () => {
        const section = button.dataset.detailSection;
        if (
          section !== "summary"
          && section !== "positions"
          && section !== "trades"
          && section !== "snapshots"
        ) {
          return;
        }
        currentDetailSection = section;
        renderCurrentDetail();
      });
    }
  }

  async function loadAccounts(): Promise<void> {
    const browserTarget = find<HTMLDivElement>("#accountsGrid");
    if (browserTarget) {
      browserTarget.innerHTML = `<div class="empty">Loading accounts...</div>`;
    }

    let data: { accounts: AccountListItem[] };
    try {
      data = await getJson<{ accounts: AccountListItem[] }>("/api/accounts");
    } catch (err) {
      const message = `<div class="error">Failed to load accounts: ${esc(errorMessage(err, "network error"))}. Is the backend running?</div>`;
      if (browserTarget) {
        browserTarget.innerHTML = message;
      }
      const meta = find<HTMLParagraphElement>("#accountWorkspaceMeta");
      if (meta) {
        meta.textContent = "Account workspace unavailable until the backend responds.";
      }
      return;
    }

    cachedAccounts = data.accounts;
    options.onAccountsLoaded?.(cachedAccounts);

    if (!data.accounts.length) {
      renderAccountBrowser();
      populateAccountSelect();
      renderWorkspaceMeta();
      return;
    }

    if (!cachedAccounts.some((account) => account.name === currentAccountName)) {
      currentAccountName = cachedAccounts[0]?.name ?? null;
    }

    populateAccountSelect();
    renderAccountBrowser(find<HTMLInputElement>("#accountSearchInput")?.value ?? "");
    renderWorkspaceMeta();

    if (currentAccountName) {
      if (!currentDetail || currentDetail.account.name !== currentAccountName) {
        await loadAccountDetail(currentAccountName);
      } else {
        renderCurrentDetail();
      }
    }
  }

  async function loadAccountDetail(accountName: string): Promise<void> {
    currentAccountName = accountName;
    populateAccountSelect();
    renderAccountBrowser(find<HTMLInputElement>("#accountSearchInput")?.value ?? "");
    renderWorkspaceMeta();

    const target = find<HTMLDivElement>("#accountDetail");
    if (!target) return;

    target.innerHTML = `<div class="empty">Loading ${esc(accountName)}...</div>`;
    try {
      currentDetail = await getJson<AccountDetail>(`/api/accounts/${encodeURIComponent(accountName)}`);
    } catch (err) {
      target.innerHTML = `<div class="error">Failed to load account detail: ${esc(errorMessage(err, "network error"))}</div>`;
      return;
    }
    currentTradePage = 1;
    currentAnalysis = null;
    currentDetailSection = "summary";
    renderCurrentDetail();
    void loadAccountAnalysis(accountName);
  }

  async function loadAccountAnalysis(accountName: string): Promise<void> {
    const panel = find<HTMLElement>("#analysisPanel");
    if (!panel) return;
    try {
      const analysis = await getJson<AccountAnalysis>(
        `/api/accounts/${encodeURIComponent(accountName)}/analysis`,
      );
      currentAnalysis = analysis;
      const freshPanel = find<HTMLElement>("#analysisPanel") ?? panel;
      freshPanel.innerHTML = renderAnalysisPanel(analysis);
    } catch {
      const freshPanel = find<HTMLElement>("#analysisPanel") ?? panel;
      freshPanel.innerHTML = `<h4>Performance Analysis</h4><div class="muted">Analysis unavailable.</div>`;
    }
  }

  async function snapshotAll(): Promise<void> {
    await postJson<{ status: string }>("/api/actions/snapshot-all");
    await loadAccounts();
  }

  function wireActions(): void {
    const snapshotAllBtn = find<HTMLButtonElement>("#snapshotAllBtn");
    const accountSelect = find<HTMLSelectElement>("#accountSelect");
    const accountSearchInput = find<HTMLInputElement>("#accountSearchInput");
    const toggleAccountBrowserBtn = find<HTMLButtonElement>("#toggleAccountBrowserBtn");

    snapshotAllBtn?.addEventListener("click", () => {
      void snapshotAll();
    });

    accountSelect?.addEventListener("change", () => {
      if (!accountSelect.value) {
        return;
      }
      void loadAccountDetail(accountSelect.value);
    });

    accountSearchInput?.addEventListener("input", () => {
      renderAccountBrowser(accountSearchInput.value);
    });

    toggleAccountBrowserBtn?.addEventListener("click", () => {
      accountBrowserOpen = !accountBrowserOpen;
      updateAccountBrowserToggle();
    });

    updateAccountBrowserToggle();
  }

  return {
    getAccounts: () => cachedAccounts,
    loadAccounts,
    loadAccountDetail,
    snapshotAll,
    wireActions,
  };
}
