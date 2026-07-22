import { currency, num, pct } from "../lib/format";
import { getJson, errorMessage } from "../lib/http";
import type {
  AutonomyAccountOverview,
  AutonomyBook,
  AutonomyDailyWorkflow,
  GovernanceCheckStatus,
  BurnInStatus,
  RotationDecision,
  RiskSummary,
  RiskViolation,
} from "../types/autonomy-monitor";

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

export function renderAccountOverview(account: AutonomyAccountOverview["account"]): string {
  const returnClass = account.return_pct >= 0 ? "up" : "down";
  
  return `
    <section class="card account-overview-card">
      <div class="card-header">
        <h3>Account Overview</h3>
      </div>
      <div class="overview-grid">
        <div class="overview-item">
          <span class="label">Total Equity</span>
          <strong class="value">${currency.format(account.total_equity)}</strong>
        </div>
        <div class="overview-item">
          <span class="label">Available Cash</span>
          <strong class="value">${currency.format(account.total_cash)}</strong>
        </div>
        <div class="overview-item">
          <span class="label">Positions Value</span>
          <strong class="value">${currency.format(account.positions_market_value)}</strong>
        </div>
        <div class="overview-item ${returnClass}">
          <span class="label">Total Return</span>
          <strong class="value">${num(account.total_equity - account.initial_cash)} (${pct(account.return_pct)})</strong>
        </div>
        <div class="overview-item">
          <span class="label">Books Active</span>
          <strong class="value">${account.book_count}</strong>
        </div>
        <div class="overview-item">
          <span class="label">Initial Capital</span>
          <strong class="value">${currency.format(account.initial_cash)}</strong>
        </div>
      </div>
    </section>
  `;
}

export function renderBooksPanel(books: AutonomyBook[]): string {
  if (books.length === 0) {
    return '<section class="card books-card"><p>No books configured</p></section>';
  }
  
  const rows = books.map(s => {
    const statusClass = s.status === "active" ? "active" : s.status === "paused" ? "paused" : "closed";
    const bookReturnClass = s.return_pct >= 0 ? "up" : "down";
    
    return `
      <tr class="book-row status-${statusClass}">
        <td class="name">${s.name}</td>
        <td class="strategy">${s.strategy}</td>
        <td class="equity">${currency.format(s.current_equity)}</td>
        <td class="cash">${currency.format(s.current_cash)}</td>
        <td class="return ${bookReturnClass}">${pct(s.return_pct)}</td>
        <td class="metrics">
          ${s.latest_metrics.hit_rate ? `Hit Rate: ${pct(s.latest_metrics.hit_rate)}` : "—"}
        </td>
        <td class="status"><span class="badge status-${statusClass}">${s.status}</span></td>
      </tr>
    `;
  }).join("");
  
  return `
    <section class="card books-card">
      <div class="card-header">
        <h3>Strategy Books</h3>
      </div>
      <table class="books-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Strategy</th>
            <th>Equity</th>
            <th>Cash</th>
            <th>Return</th>
            <th>Metrics</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          ${rows}
        </tbody>
      </table>
    </section>
  `;
}

export function renderDailyWorkflowPanel(workflow: AutonomyDailyWorkflow | null): string {
  if (!workflow) {
    return '<section class="card workflow-card"><p>No workflow data available</p></section>';
  }
  
  const statusClass = workflow.status === "success" ? "success" : workflow.status === "failed" ? "failed" : "pending";
  const latestRunTime = workflow.latest_run_time ? new Date(workflow.latest_run_time).toLocaleString() : "—";
  
  const stepsSummary = workflow.step_results ? 
    `${workflow.completed_steps} / ${workflow.step_results.length} steps completed` : 
    "—";
  
  return `
    <section class="card workflow-card">
      <div class="card-header">
        <h3>Daily Workflow Status</h3>
      </div>
      <div class="workflow-summary status-${statusClass}">
        <div class="item">
          <span class="label">Latest Run</span>
          <span class="value">${latestRunTime}</span>
        </div>
        <div class="item">
          <span class="label">Status</span>
          <span class="value status-badge status-${statusClass}">${workflow.status || "unknown"}</span>
        </div>
        <div class="item">
          <span class="label">Steps</span>
          <span class="value">${stepsSummary}</span>
        </div>
        ${workflow.duration_seconds ? `
          <div class="item">
            <span class="label">Duration</span>
            <span class="value">${workflow.duration_seconds.toFixed(1)}s</span>
          </div>
        ` : ""}
      </div>
      ${workflow.failed_step ? `
        <div class="error-box">
          <strong>Failed Step:</strong> ${workflow.failed_step}
        </div>
      ` : ""}
    </section>
  `;
}

export function renderGovernancePanel(governance: Record<string, GovernanceCheckStatus>): string {
  const jobs = [
    { key: "w1_leaderboard", label: "W1 Leaderboard", freq: "Weekly" },
    { key: "w2_promotion", label: "W2 Promotion", freq: "Weekly" },
    { key: "w3_allocation", label: "W3 Allocation", freq: "Weekly" },
    { key: "m1_risk_rebaseline", label: "M1 Risk Baseline", freq: "Monthly" },
    { key: "m2_parameter_governance", label: "M2 Parameters", freq: "Monthly" },
    { key: "m3_performance_audit", label: "M3 Performance", freq: "Monthly" },
  ];
  
  const govCards = jobs.map(job => {
    const govData = governance[job.key] || { last_run: null, status: "not_run" as const, has_results: false };
    const statusClass = govData.status === "success" ? "success" : govData.status === "failed" ? "failed" : "not_run";
    const lastRun = govData.last_run ? new Date(govData.last_run).toLocaleDateString() : "Never";
    
    return `
      <div class="governance-card status-${statusClass}">
        <div class="gov-title">${job.label}</div>
        <div class="gov-freq">${job.freq}</div>
        <div class="gov-status badge status-${statusClass}">${govData.status}</div>
        <div class="gov-lastrun">Last: ${lastRun}</div>
      </div>
    `;
  }).join("");
  
  return `
    <section class="card governance-card">
      <div class="card-header">
        <h3>Governance Checks</h3>
      </div>
      <div class="governance-grid">
        ${govCards}
      </div>
    </section>
  `;
}

export function renderBurnInPanel(burnIn: BurnInStatus): string {
  const progress = burnIn.consecutive_successes || 0;
  const required = burnIn.min_required_successes || 10;
  const progressPct = Math.min((progress / required) * 100, 100);
  const readyClass = burnIn.ready_for_live ? "ready" : "not-ready";
  
  return `
    <section class="card burn-in-card">
      <div class="card-header">
        <h3>Burn-In Progress</h3>
      </div>
      <div class="burn-in-summary ${readyClass}">
        <div class="progress-section">
          <div class="progress-label">Consecutive Successful Days</div>
          <div class="progress-bar-container">
            <div class="progress-bar" style="width: ${progressPct}%"></div>
            <span class="progress-text">${progress}/${required}</span>
          </div>
        </div>
        <div class="burn-in-stats">
          <div class="stat">
            <span class="label">Failures in Window</span>
            <span class="value">${burnIn.failure_count || 0}</span>
          </div>
          <div class="stat">
            <span class="label">Status</span>
            <span class="value badge ${readyClass}">${burnIn.ready_for_live ? "Ready for Live" : "Not Ready"}</span>
          </div>
          ${burnIn.status_as_of ? `
            <div class="stat">
              <span class="label">As of</span>
              <span class="value">${new Date(burnIn.status_as_of).toLocaleString()}</span>
            </div>
          ` : ""}
        </div>
      </div>
    </section>
  `;
}

export function renderRotationsPanel(rotations: RotationDecision[]): string {
  if (rotations.length === 0) {
    return '<section class="card rotations-card"><p>No recent rotations</p></section>';
  }
  
  const rows = rotations.slice(0, 10).map((r: RotationDecision) => `
    <tr>
      <td>${r.book_name}</td>
      <td>${r.incumbent}</td>
      <td>→ ${r.challenger}</td>
      <td>${r.reason || "—"}</td>
      <td>${new Date(r.decision_time).toLocaleDateString()}</td>
    </tr>
  `).join("");
  
  return `
    <section class="card rotations-card">
      <div class="card-header">
        <h3>Recent Rotations</h3>
      </div>
      <table class="rotations-table">
        <thead>
          <tr>
            <th>Book</th>
            <th>Incumbent</th>
            <th>Transition</th>
            <th>Reason</th>
            <th>Date</th>
          </tr>
        </thead>
        <tbody>
          ${rows}
        </tbody>
      </table>
    </section>
  `;
}

export function renderRiskSummaryPanel(riskSummary: RiskSummary): string {
  const killSwitchClass = riskSummary.kill_switch_triggered ? "triggered" : "normal";
  const violations = riskSummary.recent_violations || [];
  
  const violationRows = violations.slice(0, 5).map((v: RiskViolation) => `
    <tr class="violation-row action-${v.action}">
      <td>${v.book_name}</td>
      <td>${v.reason}</td>
      <td><span class="badge action-${v.action}">${v.action.toUpperCase()}</span></td>
      <td>${new Date(v.decision_time).toLocaleString()}</td>
    </tr>
  `).join("");
  
  return `
    <section class="card risk-card">
      <div class="card-header">
        <h3>Risk Summary</h3>
      </div>
      <div class="risk-summary">
        <div class="kill-switch ${killSwitchClass}">
          <strong>Kill Switch:</strong> 
          <span class="status ${killSwitchClass}">
            ${riskSummary.kill_switch_triggered ? "🔴 TRIGGERED" : "🟢 Normal"}
          </span>
        </div>
        ${violations.length > 0 ? `
          <div class="violations-section">
            <strong>Recent Violations (${violations.length}):</strong>
            <table class="violations-table">
              <thead>
                <tr>
                  <th>Book</th>
                  <th>Reason</th>
                  <th>Action</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                ${violationRows}
              </tbody>
            </table>
          </div>
        ` : "<p>No recent violations</p>"}
      </div>
    </section>
  `;
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
