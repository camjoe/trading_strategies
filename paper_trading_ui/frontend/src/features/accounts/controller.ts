import { find } from "../../lib/dom";
import { esc } from "../../lib/format";
import { errorMessage, getJson, postJson } from "../../lib/http";
import { renderAnalysisPanel } from "../../components/detail";
import type { AccountAnalysis, AccountDetail, AccountListItem } from "../../types";
import { populateAccountSelect, renderAccountBrowser, renderWorkspaceMeta, updateAccountBrowserToggle } from "./browser";
import { applyCachedAnalysis, renderCurrentDetail } from "./detail";
import type { AccountsFeature, AccountsFeatureOptions, AccountsState, LoadAccountDetailOptions } from "./types";

export function createAccountsController(options: AccountsFeatureOptions = {}): AccountsFeature {
  const state: AccountsState = {
    cachedAccounts: [],
    currentDetail: null,
    currentAccountName: null,
    currentTradePage: 1,
    currentAnalysis: null,
    currentDetailSection: "summary",
    accountBrowserOpen: false,
    tradePageSize: 20,
  };

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

    state.cachedAccounts = data.accounts;
    await options.onAccountsLoaded?.(state.cachedAccounts);

    if (!state.cachedAccounts.length) {
      renderAccountBrowser(state, { onOpenAccount: openAccountFromBrowser });
      populateAccountSelect(state);
      renderWorkspaceMeta(state);
      return;
    }

    if (!state.cachedAccounts.some((account) => account.name === state.currentAccountName)) {
      state.currentAccountName = state.cachedAccounts[0]?.name ?? null;
    }

    populateAccountSelect(state);
    renderAccountBrowser(state, {
      onOpenAccount: openAccountFromBrowser,
    }, find<HTMLInputElement>("#accountSearchInput")?.value ?? "");
    renderWorkspaceMeta(state);

    if (state.currentAccountName) {
      if (!state.currentDetail || state.currentDetail.account.name !== state.currentAccountName) {
        await loadAccountDetail(state.currentAccountName);
      } else {
        renderCurrentDetail(state, options, { loadAccounts, loadAccountDetail });
      }
    }
  }

  async function loadAccountDetail(
    accountName: string,
    detailOptions: LoadAccountDetailOptions = {},
  ): Promise<void> {
    state.currentAccountName = accountName;
    populateAccountSelect(state);
    renderAccountBrowser(state, {
      onOpenAccount: openAccountFromBrowser,
    }, find<HTMLInputElement>("#accountSearchInput")?.value ?? "");
    renderWorkspaceMeta(state);

    const target = find<HTMLDivElement>("#accountDetail");
    if (!target) return;

    target.innerHTML = `<div class="empty">Loading ${esc(accountName)}...</div>`;
    try {
      state.currentDetail = await getJson<AccountDetail>(`/api/accounts/${encodeURIComponent(accountName)}`);
    } catch (err) {
      target.innerHTML = `<div class="error">Failed to load account detail: ${esc(errorMessage(err, "network error"))}</div>`;
      return;
    }

    state.currentTradePage = 1;
    state.currentAnalysis = null;
    state.currentDetailSection = detailOptions.section ?? "summary";
    renderCurrentDetail(state, options, { loadAccounts, loadAccountDetail });
    void loadAccountAnalysis(accountName);
  }

  async function loadAccountAnalysis(accountName: string): Promise<void> {
    const panel = find<HTMLElement>("#analysisPanel");
    if (!panel) return;
    try {
      state.currentAnalysis = await getJson<AccountAnalysis>(
        `/api/accounts/${encodeURIComponent(accountName)}/analysis`,
      );
      const freshPanel = find<HTMLElement>("#analysisPanel") ?? panel;
      freshPanel.innerHTML = renderAnalysisPanel(state.currentAnalysis);
    } catch {
      const freshPanel = find<HTMLElement>("#analysisPanel") ?? panel;
      freshPanel.innerHTML = `<h4>Performance Analysis</h4><div class="muted">Analysis unavailable.</div>`;
    }
  }

  async function snapshotAll(): Promise<void> {
    await postJson<{ status: string }>("/api/actions/snapshot-all");
    await loadAccounts();
  }

  async function openAccountFromBrowser(accountName: string): Promise<void> {
    state.accountBrowserOpen = false;
    updateAccountBrowserToggle(state);
    await loadAccountDetail(accountName);
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
      renderAccountBrowser(state, {
        onOpenAccount: openAccountFromBrowser,
      }, accountSearchInput.value);
    });

    toggleAccountBrowserBtn?.addEventListener("click", () => {
      state.accountBrowserOpen = !state.accountBrowserOpen;
      updateAccountBrowserToggle(state);
    });

    updateAccountBrowserToggle(state);
    applyCachedAnalysis(state);
  }

  return {
    getAccounts: () => state.cachedAccounts,
    loadAccounts,
    loadAccountDetail,
    snapshotAll,
    wireActions,
  };
}
