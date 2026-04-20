import { find, findAll } from "../../lib/dom";
import { esc } from "../../lib/format";
import { accountCard } from "../../components/accounts";
import type { AccountsState } from "./types";

export function getSelectedAccount(state: AccountsState) {
  if (!state.currentAccountName) {
    return null;
  }
  return state.cachedAccounts.find((account) => account.name === state.currentAccountName) ?? null;
}

export function updateAccountBrowserToggle(state: AccountsState): void {
  const button = find<HTMLButtonElement>("#toggleAccountBrowserBtn");
  const panel = find<HTMLDivElement>("#accountBrowserPanel");
  if (!button || !panel) {
    return;
  }

  panel.hidden = !state.accountBrowserOpen;
  button.textContent = state.accountBrowserOpen ? "Hide Account Browser" : "Browse Accounts";
  button.setAttribute("aria-expanded", String(state.accountBrowserOpen));
}

export function renderAccountBrowser(
  state: AccountsState,
  handlers: { onOpenAccount: (accountName: string) => Promise<void> },
  searchTerm = "",
): void {
  const target = find<HTMLDivElement>("#accountsGrid");
  if (!target) return;

  const normalized = searchTerm.trim().toLowerCase();
  const visibleAccounts = state.cachedAccounts.filter((account) => {
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
    .map((account) => accountCard(account, { selected: account.name === state.currentAccountName }))
    .join("");

  for (const btn of findAll<HTMLButtonElement>(".account-card")) {
    btn.addEventListener("click", () => {
      const accountName = btn.dataset.account;
      if (!accountName) return;
      void handlers.onOpenAccount(accountName);
    });
  }
}

export function populateAccountSelect(state: AccountsState): void {
  const select = find<HTMLSelectElement>("#accountSelect");
  if (!select) return;

  if (!state.cachedAccounts.length) {
    select.innerHTML = `<option value="">No accounts</option>`;
    return;
  }

  select.innerHTML = state.cachedAccounts
    .map((account) => `<option value="${esc(account.name)}">${esc(account.displayName)} (${esc(account.name)})</option>`)
    .join("");

  if (state.currentAccountName) {
    select.value = state.currentAccountName;
  }
}

export function renderWorkspaceMeta(state: AccountsState): void {
  const meta = find<HTMLParagraphElement>("#accountWorkspaceMeta");
  if (!meta) return;

  const account = getSelectedAccount(state);
  if (!account) {
    meta.textContent = state.cachedAccounts.length
      ? "Select an account to focus the workspace."
      : "No accounts found in the paper trading database.";
    return;
  }

  meta.textContent = `${account.displayName} (${account.name}) - ${account.strategy} vs ${account.benchmark}.`;
}
