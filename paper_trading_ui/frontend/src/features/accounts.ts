import { find, findAll } from "../lib/dom";
import { esc } from "../lib/format";
import { getJson, postJson } from "../lib/http";
import { accountCard } from "../templates/accounts";
import { renderDetail } from "../templates/detail";
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
        await options.onOpenRunReport?.(runId);
      });
    }
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
