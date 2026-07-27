import { currency, esc } from "../../lib/format";
import type { AccountDetail } from "../../types/accounts";
import type { DetailSectionName } from "./types";

export function renderSummarySection(
  activeSection: DetailSectionName,
  detail: AccountDetail,
  options: { showBacktest: boolean; latestBacktest: string },
): string {
  const latestSnapshot = detail.snapshots[0] ?? null;
  const latestTrade = detail.trades[detail.trades.length - 1] ?? null;
  const snapshotTime = latestSnapshot ? new Date(latestSnapshot.time).toLocaleString() : "—";
  const tradeTime = latestTrade ? new Date(latestTrade.tradeTime).toLocaleString() : "—";
  const snapshotChange = detail.account.changeSinceLastSnapshot;
  const changeText = snapshotChange == null
    ? "—"
    : `${snapshotChange >= 0 ? "+" : ""}${currency.format(snapshotChange)}`;
  const latestMetric = detail.bookMetrics?.[0] ?? null;
  const riskDecisions = detail.riskDecisions ?? [];
  const operationalSummary = latestMetric || riskDecisions.length
    ? `<section class="summary-overview-card">
        <h4>Book Operations</h4>
        <div class="analysis-summary">
          <div class="analysis-stat"><span class="label">Metric Date</span><span>${esc(latestMetric?.metricDate ?? "—")}</span></div>
          <div class="analysis-stat"><span class="label">Return</span><span>${latestMetric?.returnPct == null ? "—" : `${latestMetric.returnPct.toFixed(2)}%`}</span></div>
          <div class="analysis-stat"><span class="label">Drawdown</span><span>${latestMetric?.drawdownPct == null ? "—" : `${latestMetric.drawdownPct.toFixed(2)}%`}</span></div>
          <div class="analysis-stat"><span class="label">Risk-adjusted Score</span><span>${latestMetric?.riskAdjustedScore?.toFixed(2) ?? "—"}</span></div>
          <div class="analysis-stat"><span class="label">Recent Risk Decisions</span><span>${riskDecisions.length}</span></div>
          <div class="analysis-stat"><span class="label">Latest Decision</span><span>${riskDecisions[0] ? `${esc(riskDecisions[0].action)} — ${esc(riskDecisions[0].reason)}` : "—"}</span></div>
        </div>
      </section>`
    : "";

  return `
    <article class="detail-section-panel" data-detail-panel="summary" ${activeSection === "summary" ? "" : "hidden"}>
      <div class="summary-overview-grid">
        <section class="summary-overview-card">
          <h4>Current Posture</h4>
          <div class="analysis-summary">
            <div class="analysis-stat">
              <span class="label">Open Positions</span>
              <span>${detail.positions.length}</span>
            </div>
            <div class="analysis-stat">
              <span class="label">Recent Trades</span>
              <span>${detail.trades.length}</span>
            </div>
            <div class="analysis-stat">
              <span class="label">Latest Snapshot</span>
              <span>${snapshotTime}</span>
            </div>
            <div class="analysis-stat">
              <span class="label">Change Since Snapshot</span>
              <span class="${snapshotChange != null && snapshotChange < 0 ? "down" : "up"}">${changeText}</span>
            </div>
            <div class="analysis-stat">
              <span class="label">Last Trade</span>
              <span>${tradeTime}</span>
            </div>
          </div>
        </section>
        <section class="summary-overview-card">
          <h4>Portfolio Snapshot</h4>
          <div class="analysis-summary">
            <div class="analysis-stat">
              <span class="label">Cash</span>
              <span>${currency.format(latestSnapshot?.cash ?? detail.account.settlementCash)}</span>
            </div>
            <div class="analysis-stat">
              <span class="label">Market Value</span>
              <span>${currency.format(latestSnapshot?.marketValue ?? 0)}</span>
            </div>
            <div class="analysis-stat">
              <span class="label">Realized P&amp;L</span>
              <span>${latestSnapshot ? currency.format(latestSnapshot.realizedPnl) : "—"}</span>
            </div>
            <div class="analysis-stat">
              <span class="label">Unrealized P&amp;L</span>
              <span>${latestSnapshot ? currency.format(latestSnapshot.unrealizedPnl) : "—"}</span>
            </div>
          </div>
        </section>
        ${operationalSummary}
      </div>
      ${options.showBacktest ? `<div class="latest-backtest-section">
        <h4>Latest Backtest</h4>
        ${options.latestBacktest}
      </div>` : ""}
    </article>
  `;
}

export function renderAnalysisSection(activeSection: DetailSectionName): string {
  return `
    <article class="detail-section-panel" data-detail-panel="analysis" ${activeSection === "analysis" ? "" : "hidden"}>
      <div id="analysisPanel">
        <h4>Performance Analysis</h4>
        <div class="empty">Loading analysis…</div>
      </div>
    </article>
  `;
}
