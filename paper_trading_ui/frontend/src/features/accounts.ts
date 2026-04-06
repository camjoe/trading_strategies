import { find, findAll } from "../lib/dom";
import { esc } from "../lib/format";
import { getJson, patchJson, postJson } from "../lib/http";
import { accountCard } from "../components/accounts";
import { renderDetail } from "../components/detail";
import type { AccountDetail, AccountParamsUpdate, AccountSummary } from "../types";

export interface AccountsFeatureOptions {
  onAccountsLoaded?: (accounts: AccountSummary[]) => void;
  onOpenRunReport?: (runId: number) => Promise<void> | void;
}

export interface AccountsFeature {
  getAccounts: () => AccountSummary[];
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

function parseRunId(raw: string | undefined): number | null {
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

export function createAccountsFeature(options: AccountsFeatureOptions = {}): AccountsFeature {
  let cachedAccounts: AccountSummary[] = [];
  let currentDetail: AccountDetail | null = null;
  let currentTradePage = 1;
  const tradePageSize = 20;

  function renderCurrentDetail(): void {
    const target = find<HTMLDivElement>("#accountDetail");
    if (!target || !currentDetail) return;

    target.innerHTML = renderDetail(currentDetail, {
      tradePage: currentTradePage,
      tradePageSize,
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
          msgEl.textContent = err instanceof Error ? err.message : "Save failed.";
        }
      }
    });
  }

  async function loadAccounts(): Promise<void> {
    const target = find<HTMLDivElement>("#accountsGrid");
    if (!target) return;

    target.innerHTML = `<div class="empty">Loading accounts...</div>`;

    let data: { accounts: AccountSummary[] };
    try {
      data = await getJson<{ accounts: AccountSummary[] }>("/api/accounts");
    } catch (err) {
      target.innerHTML = `<div class="error">Failed to load accounts: ${esc(err instanceof Error ? err.message : "network error")}. Is the backend running?</div>`;
      return;
    }

    cachedAccounts = data.accounts;
    options.onAccountsLoaded?.(cachedAccounts);

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
    try {
      currentDetail = await getJson<AccountDetail>(`/api/accounts/${encodeURIComponent(accountName)}`);
    } catch (err) {
      target.innerHTML = `<div class="error">Failed to load account detail: ${esc(err instanceof Error ? err.message : "network error")}</div>`;
      return;
    }
    currentTradePage = 1;
    renderCurrentDetail();
  }

  async function snapshotAll(): Promise<void> {
    await postJson<{ status: string }>("/api/actions/snapshot-all");
    await loadAccounts();
  }

  function wireActions(): void {
    const snapshotAllBtn = find<HTMLButtonElement>("#snapshotAllBtn");

    snapshotAllBtn?.addEventListener("click", () => {
      void snapshotAll();
    });
  }

  return {
    getAccounts: () => cachedAccounts,
    loadAccounts,
    loadAccountDetail,
    snapshotAll,
    wireActions,
  };
}
