import { find, findAll } from "../lib/dom";
import { esc } from "../lib/format";
import { getJson, postJson } from "../lib/http";
import { accountCard } from "../components/accounts";
import { renderDetail } from "../components/detail";
import type { AccountDetail, AccountSummary } from "../types";

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
        await options.onOpenRunReport?.(runId);
      });
    }

    const newerTradesBtn = find<HTMLButtonElement>("#recentTradesPrevBtn");
    if (newerTradesBtn) {
      newerTradesBtn.addEventListener("click", () => {
        currentTradePage = Math.max(1, currentTradePage - 1);
        renderCurrentDetail();
      });
    }

    const olderTradesBtn = find<HTMLButtonElement>("#recentTradesNextBtn");
    if (olderTradesBtn) {
      olderTradesBtn.addEventListener("click", () => {
        if (!currentDetail) return;
        const totalPages = Math.max(1, Math.ceil(currentDetail.trades.length / tradePageSize));
        currentTradePage = Math.min(totalPages, currentTradePage + 1);
        renderCurrentDetail();
      });
    }
  }

  async function loadAccounts(): Promise<void> {
    const target = find<HTMLDivElement>("#accountsGrid");
    if (!target) return;

    target.innerHTML = `<div class="empty">Loading accounts...</div>`;
    const data = await getJson<{ accounts: AccountSummary[] }>("/api/accounts");
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
    currentDetail = await getJson<AccountDetail>(`/api/accounts/${encodeURIComponent(accountName)}`);
    currentTradePage = 1;
    renderCurrentDetail();
  }

  async function snapshotAll(): Promise<void> {
    await postJson<{ status: string }>("/api/actions/snapshot-all");
    await loadAccounts();
  }

  function wireActions(): void {
    const refreshBtn = find<HTMLButtonElement>("#refreshAccountsBtn");
    const snapshotAllBtn = find<HTMLButtonElement>("#snapshotAllBtn");

    refreshBtn?.addEventListener("click", () => {
      void loadAccounts();
    });

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
