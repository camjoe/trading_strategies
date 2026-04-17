import { esc } from "../lib/format";
import type {
  OperationArtifact,
  OperationJobStatus,
  OperationsOverviewResponse,
  PromotionOverviewResponse,
} from "../types";

function formatDate(value: string | null | undefined): string {
  if (!value) return "never";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function formatBytes(sizeBytes: number): string {
  if (sizeBytes >= 1024 * 1024) return `${(sizeBytes / (1024 * 1024)).toFixed(2)} MB`;
  if (sizeBytes >= 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`;
  return `${sizeBytes} B`;
}

function statusLabel(status: OperationJobStatus["status"]): string {
  if (status === "ok") return "Healthy";
  if (status === "warning") return "Attention";
  return "Missing";
}

function renderJobCard(job: OperationJobStatus): string {
  const currentText = job.currentRunComplete
    ? `Completed in ${job.windowLabel}.`
    : job.currentRunPresent
      ? `A run exists for ${job.windowLabel}, but the completion sentinel was not found.`
      : `No run logged for ${job.windowLabel}.`;
  const currentLog = job.currentLog
    ? `<div class="ops-card-meta">Current log: <code>${esc(job.currentLog.name)}</code> · ${esc(formatDate(job.currentLog.modifiedAt))}</div>`
    : `<div class="ops-card-meta">Current log: none</div>`;
  const lastSuccess = job.lastSuccess
    ? `<div class="ops-card-meta">Last success: <code>${esc(job.lastSuccess.name)}</code> · ${esc(formatDate(job.lastSuccess.modifiedAt))}</div>`
    : `<div class="ops-card-meta">Last success: never found</div>`;
  return `
    <article class="ops-status-card">
      <div class="ops-card-head">
        <strong>${esc(job.label)}</strong>
        <span class="status-pill ${esc(job.status)}">${esc(statusLabel(job.status))}</span>
      </div>
      <div class="ops-card-meta">${esc(job.cadence)} window · ${esc(job.windowLabel)}</div>
      <p class="ops-card-copy">${esc(currentText)}</p>
      ${currentLog}
      ${lastSuccess}
      <div class="ops-card-hint"><span>Run hint</span><code>${esc(job.runHint)}</code></div>
    </article>
  `;
}

function renderArtifactPanel(title: string, emptyText: string, artifacts: OperationArtifact[]): string {
  if (!artifacts.length) {
    return `
      <section class="ops-artifact-panel">
        <h3>${esc(title)}</h3>
        <div class="empty">${esc(emptyText)}</div>
      </section>
    `;
  }
  return `
    <section class="ops-artifact-panel">
      <h3>${esc(title)}</h3>
      <ul class="ops-artifact-list">
        ${artifacts
          .map(
            (artifact) => `
              <li>
                <strong>${esc(artifact.name)}</strong>
                <span>${esc(formatDate(artifact.modifiedAt))}</span>
                <span>${esc(formatBytes(artifact.sizeBytes))}</span>
              </li>
            `,
          )
          .join("")}
      </ul>
    </section>
  `;
}

export function renderOperationsOverview(data: OperationsOverviewResponse): string {
  return `
    <div class="ops-status-grid">
      ${data.jobs.map(renderJobCard).join("")}
    </div>
    <div class="ops-artifact-grid">
      ${renderArtifactPanel(
        "Scheduled Backtest Refresh Artifacts",
        "No scheduled refresh artifacts found in local/exports/scheduled_backtest_refresh yet.",
        data.scheduledRefreshArtifacts,
      )}
      ${renderArtifactPanel(
        "Daily Snapshot Artifacts",
        "No daily snapshot artifacts found in local/exports/daily_snapshots yet.",
        data.dailySnapshotArtifacts,
      )}
      ${renderArtifactPanel(
        "Database Backups",
        "No database backups found in local/db_backups yet.",
        data.databaseBackups,
      )}
    </div>
  `;
}

function renderTextList(title: string, items: string[], emptyText: string): string {
  if (!items.length) {
    return `
      <section class="promotion-section">
        <h4>${esc(title)}</h4>
        <div class="empty">${esc(emptyText)}</div>
      </section>
    `;
  }
  return `
    <section class="promotion-section">
      <h4>${esc(title)}</h4>
      <ul class="promotion-list">
        ${items.map((item) => `<li>${esc(item)}</li>`).join("")}
      </ul>
    </section>
  `;
}

export function renderPromotionOverview(data: PromotionOverviewResponse): string {
  const assessment = data.assessment;
  const historyHtml = data.history.length
    ? data.history
        .map(
          (entry) => `
            <article class="promotion-history-card">
              <div class="ops-card-head">
                <strong>Review #${entry.review.id ?? "?"}</strong>
                <span class="status-pill ${entry.review.review_state === "approved" ? "ok" : entry.review.review_state === "requested" ? "warning" : "missing"}">${esc(entry.review.review_state)}</span>
              </div>
              <div class="promotion-review-meta">
                ${esc(entry.review.account_name_snapshot ?? assessment.account_name ?? "Unknown account")} / ${esc(entry.review.strategy_name ?? assessment.strategy_name ?? "Unknown strategy")}
              </div>
              <div class="promotion-review-meta">
                Requested by ${esc(entry.review.requested_by ?? "unknown")} · Updated ${esc(formatDate(entry.review.updated_at ?? entry.review.created_at))}
              </div>
              <div class="promotion-review-meta">
                Confidence ${entry.review.overall_confidence.toFixed(2)} · Ready for live ${entry.review.ready_for_live ? "yes" : "no"}
              </div>
              ${
                entry.review.operator_summary_note
                  ? `<p class="ops-card-copy">${esc(entry.review.operator_summary_note)}</p>`
                  : ""
              }
              <div class="promotion-events">
                ${
                  entry.events.length
                    ? entry.events
                        .map(
                          (event) => `
                            <div class="promotion-event-row">
                              <strong>${esc(event.event_type)}</strong>
                              <span>${esc(formatDate(event.created_at))}</span>
                              <span>${esc(event.actor_name ?? "unknown")}</span>
                              <span>${esc(event.from_review_state ?? "none")} -> ${esc(event.to_review_state ?? "none")}</span>
                              ${event.note ? `<div class="promotion-event-note">${esc(event.note)}</div>` : ""}
                            </div>
                          `,
                        )
                        .join("")
                    : `<div class="empty">No persisted review events yet.</div>`
                }
              </div>
            </article>
          `,
        )
        .join("")
    : `<div class="empty">No persisted promotion reviews found for this account yet.</div>`;

  return `
    <div class="promotion-summary-grid">
      <div class="analysis-stat">
        <span class="label">Stage</span>
        <span>${esc(assessment.stage)}</span>
      </div>
      <div class="analysis-stat">
        <span class="label">Status</span>
        <span>${esc(assessment.status)}</span>
      </div>
      <div class="analysis-stat">
        <span class="label">Ready for Live</span>
        <span>${assessment.ready_for_live ? "yes" : "no"}</span>
      </div>
      <div class="analysis-stat">
        <span class="label">Confidence</span>
        <span>${assessment.overall_confidence.toFixed(2)}</span>
      </div>
      <div class="analysis-stat">
        <span class="label">Evaluation</span>
        <span>${esc(formatDate(assessment.evaluation_generated_at))}</span>
      </div>
      <div class="analysis-stat">
        <span class="label">Next Action</span>
        <span>${esc(assessment.next_action ?? "None recorded")}</span>
      </div>
    </div>
    ${renderTextList("Blockers", assessment.blockers, "No blockers recorded.")}
    ${renderTextList("Warnings", assessment.warnings, "No warnings recorded.")}
    ${renderTextList("Data Gaps", assessment.data_gaps, "No data gaps recorded.")}
    <section class="promotion-section">
      <h4>Recent Review History</h4>
      <div class="promotion-history-stack">${historyHtml}</div>
    </section>
  `;
}
