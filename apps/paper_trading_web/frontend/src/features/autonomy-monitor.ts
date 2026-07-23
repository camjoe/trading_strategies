import {
  renderAccountOverview,
  renderBooksPanel,
  renderBurnInPanel,
  renderDailyWorkflowPanel,
  renderGovernancePanel,
  renderRiskSummaryPanel,
  renderRotationsPanel,
} from "../components/autonomy-monitor-panels";
import { errorMessage, getJson } from "../lib/http";
import type { AutonomyAccountOverview } from "../types/autonomy-monitor";

interface AutonomyMonitorState {
  accounts: Array<{ name: string; total_equity: number; book_count: number }>;
  selectedAccount: string | null;
  currentData: AutonomyAccountOverview | null;
  loading: boolean;
  error: string | null;
  lastRefresh: Date | null;
}

const state: AutonomyMonitorState = {
  accounts: [],
  selectedAccount: null,
  currentData: null,
  loading: false,
  error: null,
  lastRefresh: null,
};

async function fetchAccounts(): Promise<void> {
  try {
    const response = await getJson<{ accounts: Array<{ name: string; total_equity: number; book_count: number }> }>("/api/autonomy/accounts");
    state.accounts = response.accounts || [];
    updateAccountSelect();
  } catch (err) {
    state.error = `Failed to load accounts: ${errorMessage(err)}`;
    console.error(state.error);
  }
}

async function fetchAccountData(accountName: string): Promise<void> {
  if (!accountName) return;

  state.loading = true;
  state.error = null;

  try {
    state.currentData = await getJson<AutonomyAccountOverview>(`/api/autonomy/accounts/${encodeURIComponent(accountName)}`);
    state.lastRefresh = new Date();
    renderDashboard();
  } catch (err) {
    state.error = `Failed to load account data: ${errorMessage(err)}`;
    console.error(state.error);
    renderError();
  } finally {
    state.loading = false;
  }
}

function updateAccountSelect(): void {
  const select = document.getElementById("autonomyAccountSelect") as HTMLSelectElement | null;
  if (!select) return;

  select.innerHTML = '<option value="">-- Select Account --</option>' +
    state.accounts.map(a => `<option value="${a.name}">${a.name} (${a.book_count} books)</option>`).join("");
}

function renderError(): void {
  const dashboard = document.getElementById("autonomyDashboard");
  if (!dashboard) return;

  dashboard.innerHTML = `
    <div class="error-message">
      <p>${state.error || "Unknown error"}</p>
      <button id="retryBtn" class="btn">Retry</button>
    </div>
  `;

  const retryBtn = document.getElementById("retryBtn");
  if (retryBtn && state.selectedAccount) {
    retryBtn.addEventListener("click", () => fetchAccountData(state.selectedAccount!));
  }
}

function renderDashboard(): void {
  if (!state.currentData) {
    renderError();
    return;
  }

  const dashboard = document.getElementById("autonomyDashboard");
  if (!dashboard) return;

  const data = state.currentData;
  const account = data.account;

  dashboard.className = "autonomy-dashboard";
  dashboard.innerHTML = `
    ${renderAccountOverview(account)}
    ${renderBooksPanel(data.books || [])}
    ${renderDailyWorkflowPanel(data.daily_workflow)}
    ${renderGovernancePanel(data.governance_checks || {})}
    ${renderBurnInPanel(data.burn_in_status || {})}
    ${renderRotationsPanel(data.recent_rotations || [])}
    ${renderRiskSummaryPanel(data.risk_summary || {})}
  `;

  attachEventListeners();
}

function attachEventListeners(): void {
  const select = document.getElementById("autonomyAccountSelect") as HTMLSelectElement | null;
  if (!select) return;

  select.addEventListener("change", (e) => {
    const target = e.target as HTMLSelectElement;
    state.selectedAccount = target.value;
    if (target.value) {
      fetchAccountData(target.value);
    }
  });

  const refreshBtn = document.getElementById("autonomyRefreshBtn");
  if (refreshBtn && state.selectedAccount) {
    refreshBtn.addEventListener("click", () => fetchAccountData(state.selectedAccount!));
  }
}

export function init(): void {
  attachEventListeners();
  fetchAccounts();
}
