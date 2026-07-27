import { currency, esc, num, pct } from "../lib/format";
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

    const details = govData.result ? renderGovernanceResult(job.key, govData.result) : "";
    return `
      <div class="governance-card status-${statusClass}">
        <div class="gov-title">${job.label}</div>
        <div class="gov-freq">${job.freq}</div>
        <div class="gov-status badge status-${statusClass}">${govData.status}</div>
        <div class="gov-lastrun">Last: ${lastRun}</div>
        ${govData.has_results ? `<button class="governance-result-toggle" type="button" data-governance-key="${job.key}">View results</button>` : ""}
      </div>
      ${details}
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

function governanceValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (Array.isArray(value)) return value.map(item => String(item)).join(", ") || "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function governanceLabel(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());
}

function renderGovernanceResult(key: string, result: GovernanceCheckStatus["result"]): string {
  if (!result) return "";
  const summaryFields = Object.entries(result)
    .filter(([name, value]) => !["accounts", "generated_at", "run_timestamp", "week", "month"].includes(name) && typeof value !== "object")
    .map(([name, value]) => `<div class="analysis-stat"><span class="label">${esc(governanceLabel(name))}</span><span>${esc(governanceValue(value))}</span></div>`)
    .join("");
  const accounts = result.accounts ?? [];
  const accountHtml = accounts.map(account => {
    const accountName = account.account_name ?? "";
    const accountFields = Object.entries(account)
      .filter(([name]) => name !== "account_name" && name !== "books")
      .map(([name, value]) => `<div class="analysis-stat"><span class="label">${esc(governanceLabel(name))}</span><span>${esc(governanceValue(value))}</span></div>`)
      .join("");
    const books = (account.books ?? []).map(book => {
      const bookName = book.book_name ?? "";
      const strategyName = book.strategy_name ?? "";
      const fields = Object.entries(book)
        .filter(([name]) => name !== "book_name" && name !== "strategy_name")
        .map(([name, value]) => `<td><span class="label">${esc(governanceLabel(name))}</span><br>${esc(governanceValue(value))}</td>`)
        .join("");
      return `<tr>
        <td><button class="governance-account-link" data-account="${esc(accountName)}" data-book="${esc(bookName)}" type="button">${esc(bookName || "Book")}</button></td>
        <td>${strategyName ? `<button class="governance-strategy-link" data-strategy="${esc(strategyName)}" type="button">${esc(strategyName)}</button>` : "—"}</td>
        ${fields}
      </tr>`;
    }).join("");
    return `<section class="promotion-section">
      <div class="ops-card-head">
        <h4>${esc(accountName || "Account")}</h4>
        ${accountName ? `<button class="governance-account-link" data-account="${esc(accountName)}" type="button">Open account</button>` : ""}
      </div>
      ${accountFields ? `<div class="promotion-summary-grid">${accountFields}</div>` : ""}
      ${books ? `<div class="table-scroll"><table class="ref-table"><tbody>${books}</tbody></table></div>` : ""}
    </section>`;
  }).join("");
  const period = result.week ?? result.month ?? result.generated_at ?? result.run_timestamp ?? "";
  return `<div class="governance-result-panel" data-governance-result="${key}" hidden>
    <div class="ops-card-head"><strong>${esc(governanceLabel(key))}</strong><span>${esc(period)}</span></div>
    ${key === "m2_parameter_governance" ? '<button class="governance-parameters-link" type="button">Open Parameter Governance</button>' : ""}
    ${summaryFields ? `<div class="promotion-summary-grid">${summaryFields}</div>` : ""}
    ${accountHtml || (summaryFields ? "" : '<div class="empty">The artifact contains no structured results.</div>')}
  </div>`;
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
