import { renderParameterGroups } from "../../components/admin-parameters";
import { find } from "../../lib/dom";
import { esc } from "../../lib/format";
import { errorMessage, getJson } from "../../lib/http";
import type { AccountListItem } from "../../types/accounts";
import type { ParameterSourceResponse } from "./types";

export interface AdminParametersController {
  initialize: () => Promise<void>;
  wireActions: () => void;
}

export function createAdminParametersController(): AdminParametersController {
  let groups: ParameterSourceResponse["groups"] = [];

  function render(): void {
    const output = find<HTMLElement>("#parameterViewOutput");
    const meta = find<HTMLElement>("#parameterViewMeta");
    if (!output || !meta) return;
    const result = renderParameterGroups(
      groups,
      find<HTMLInputElement>("#parameterSearchInput")?.value ?? "",
      find<HTMLSelectElement>("#parameterSourceSelect")?.value ?? "",
    );
    output.innerHTML = result.html;
    meta.textContent = `${result.entryCount} parameters across ${result.groupCount} groups.`;
  }

  async function loadParameters(): Promise<void> {
    const output = find<HTMLElement>("#parameterViewOutput");
    if (output) output.innerHTML = '<div class="empty">Loading parameters…</div>';
    const account = find<HTMLSelectElement>("#parameterAccountSelect")?.value ?? "";
    const query = account ? `?accountName=${encodeURIComponent(account)}` : "";
    try {
      const response = await getJson<ParameterSourceResponse>(`/api/admin/parameters${query}`);
      groups = response.groups;
      render();
    } catch (error) {
      if (output) output.innerHTML = `<div class="error">${errorMessage(error, "Failed to load parameters.")}</div>`;
    }
  }

  async function initialize(): Promise<void> {
    const select = find<HTMLSelectElement>("#parameterAccountSelect");
    if (select) {
      try {
        const response = await getJson<{ accounts: AccountListItem[] }>("/api/accounts");
        select.innerHTML = '<option value="">All accounts</option>'
          + response.accounts.map(account => `<option value="${esc(account.name)}">${esc(account.displayName)}</option>`).join("");
      } catch {
        select.innerHTML = '<option value="">All accounts</option>';
      }
    }
    await loadParameters();
  }

  function wireActions(): void {
    find<HTMLButtonElement>("#parameterRefreshBtn")?.addEventListener("click", () => void loadParameters());
    find<HTMLSelectElement>("#parameterAccountSelect")?.addEventListener("change", () => void loadParameters());
    find<HTMLInputElement>("#parameterSearchInput")?.addEventListener("input", render);
    find<HTMLSelectElement>("#parameterSourceSelect")?.addEventListener("change", render);
  }

  return { initialize, wireActions };
}
