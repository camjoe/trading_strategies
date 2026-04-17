import { currency, esc } from "../../lib/format";
import type { AccountDetail } from "../../types";

type DetailSectionName = "summary" | "analysis" | "positions" | "trades" | "snapshots" | "config";

export function renderDetailHeader(
  detail: AccountDetail,
  options: {
    benchmarkSummary: string;
    showActions: boolean;
    showAddTrade: boolean;
  },
): string {
  const { benchmarkSummary, showActions, showAddTrade } = options;
  return `
    <div class="detail-head">
      <div>
        <h3>${esc(detail.account.displayName)}</h3>
        <p>${esc(detail.account.name)} | ${esc(detail.account.strategy)} | ${esc(detail.account.benchmark)}</p>
        <p class="row slim">
          Equity: <strong>${currency.format(detail.account.equity)}</strong>
          &nbsp;·&nbsp; Settlement Cash: <strong>${currency.format(detail.account.settlementCash)}</strong>
          &nbsp;·&nbsp; Return: <span class="${detail.account.totalChangePct >= 0 ? "up" : "down"}">${detail.account.totalChangePct >= 0 ? "+" : ""}${detail.account.totalChangePct.toFixed(2)}%</span>
        </p>
        ${benchmarkSummary}
      </div>
      ${showActions || showAddTrade ? `<div class="detail-head-actions">
        ${showAddTrade ? `<button id="addTradeBtn" type="button">+ Add Trade</button>` : ""}
        ${showActions ? `<button id="openConfigBtn" type="button">Open Config</button>
        <button id="snapshotOneBtn" type="button" data-account="${esc(detail.account.name)}">Snapshot This Account</button>` : ""}
      </div>` : ""}
    </div>
  `;
}

export function renderSectionTabs(activeSection: DetailSectionName): string {
  const sectionTabs: Array<{ id: DetailSectionName; label: string }> = [
    { id: "summary", label: "Summary" },
    { id: "analysis", label: "Analysis" },
    { id: "positions", label: "Positions" },
    { id: "trades", label: "Trades" },
    { id: "snapshots", label: "Snapshots" },
    { id: "config", label: "Config" },
  ];

  return `
    <div class="detail-section-tabs" role="tablist" aria-label="Account workspace sections">
      ${sectionTabs
        .map(
          (section) => `
            <button
              type="button"
              class="detail-section-tab${section.id === activeSection ? " active" : ""}"
              data-detail-section="${section.id}"
              aria-selected="${String(section.id === activeSection)}"
            >
              ${section.label}
            </button>
          `,
        )
        .join("")}
    </div>
  `;
}

export function renderAddTradePanel(showAddTrade: boolean): string {
  if (!showAddTrade) {
    return "";
  }

  return `<div id="addTradePanel" class="edit-params-panel" hidden>
      <div class="edit-params-section">
        <h5>Add Trade</h5>
        <div class="bt-row">
          <div class="bt-field">
            <span>Ticker</span>
            <input id="addTradeTicker" type="text" placeholder="e.g. AAPL" style="text-transform:uppercase" />
          </div>
          <div class="bt-field">
            <span>Side</span>
            <select id="addTradeSide">
              <option value="buy">buy</option>
              <option value="sell">sell</option>
            </select>
          </div>
          <div class="bt-field">
            <span>Qty</span>
            <input id="addTradeQty" type="number" step="0.0001" min="0.0001" placeholder="e.g. 10" />
          </div>
          <div class="bt-field">
            <span>Price</span>
            <input id="addTradePrice" type="number" step="0.01" min="0.01" placeholder="e.g. 150.00" />
          </div>
          <div class="bt-field">
            <span>Fee</span>
            <input id="addTradeFee" type="number" step="0.01" min="0" value="0" />
          </div>
        </div>
      </div>
      <div class="edit-params-actions">
        <button id="addTradeSaveBtn" type="button">Submit Trade</button>
        <button id="addTradeCancelBtn" type="button">Cancel</button>
        <div id="addTradeMsg"></div>
      </div>
    </div>`;
}

export function renderSummarySection(
  activeSection: DetailSectionName,
  options: { showBacktest: boolean; latestBacktest: string },
): string {
  return `
    <article class="detail-section-panel" data-detail-panel="summary" ${activeSection === "summary" ? "" : "hidden"}>
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

export function renderPositionsSection(detail: AccountDetail, activeSection: DetailSectionName): string {
  return `
    <article class="detail-section-panel" data-detail-panel="positions" ${activeSection === "positions" ? "" : "hidden"}>
      <h4>Current Positions</h4>
      <table>
        <thead><tr><th>Ticker</th><th>Qty</th><th>Avg Cost</th><th>Market Price</th><th>Market Value</th><th>Unrealized P&amp;L</th></tr></thead>
        <tbody>${
          detail.positions.length === 0
            ? `<tr><td colspan="6">No open positions.</td></tr>`
            : detail.positions
                .map(
                  (position) => `
          <tr>
            <td><strong>${esc(position.ticker)}</strong></td>
            <td>${position.qty.toFixed(2)}</td>
            <td>${currency.format(position.avgCost)}</td>
            <td>${position.marketPrice > 0 ? currency.format(position.marketPrice) : "—"}</td>
            <td>${position.marketPrice > 0 ? currency.format(position.marketValue) : "—"}</td>
            <td class="${position.unrealizedPnl >= 0 ? "up" : "down"}">${position.marketPrice > 0 ? currency.format(position.unrealizedPnl) : "—"}</td>
          </tr>
        `,
                )
                .join("")
        }</tbody>
      </table>
    </article>
  `;
}

export function renderTradesSection(
  tradeRows: string,
  options: {
    activeSection: DetailSectionName;
    tradePage: number;
    viewedStart: number;
    viewedEnd: number;
    totalTrades: number;
    totalTradePages: number;
  },
): string {
  const { activeSection, tradePage, viewedStart, viewedEnd, totalTrades, totalTradePages } = options;
  return `
    <article class="detail-section-panel" data-detail-panel="trades" ${activeSection === "trades" ? "" : "hidden"}>
      <h4>Recent Trades</h4>
      <div class="table-pagination">
        <button id="recentTradesPrevBtn" type="button" ${tradePage <= 1 ? "disabled" : ""}>Newer</button>
        <span>${viewedStart} to ${viewedEnd} of ${totalTrades}</span>
        <button id="recentTradesNextBtn" type="button" ${tradePage >= totalTradePages ? "disabled" : ""}>Older</button>
      </div>
      <table class="recent-trades-table">
        <thead><tr><th>Time</th><th>Ticker</th><th>Side</th><th>Type</th><th>Qty</th><th>Price</th><th>Total</th></tr></thead>
        <tbody>${tradeRows || `<tr><td colspan="7">No trades yet.</td></tr>`}</tbody>
      </table>
    </article>
  `;
}

function renderEquitySparkline(
  snapshots: AccountDetail["snapshots"],
  options: { title: string },
): string {
  const { title } = options;
  if (snapshots.length < 2) {
    return `<div class="muted">${esc(title)} unavailable.</div>`;
  }

  const equities = snapshots.map((item) => item.equity);
  const minEquity = Math.min(...equities);
  const maxEquity = Math.max(...equities);
  const spread = Math.max(maxEquity - minEquity, 1);
  const width = 320;
  const height = 96;
  const pad = 8;
  const points = snapshots
    .map((item, index) => {
      const x = pad + ((width - (pad * 2)) * index) / Math.max(snapshots.length - 1, 1);
      const y = height - pad - (((item.equity - minEquity) / spread) * (height - (pad * 2)));
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return `
    <div class="bt-equity-curve">
      <div class="row slim"><strong>${esc(title)}</strong> <span>${currency.format(minEquity)} to ${currency.format(maxEquity)}</span></div>
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(title)}">
        <polyline fill="none" stroke="currentColor" stroke-width="2" points="${points}" />
      </svg>
    </div>
  `;
}

function renderBenchmarkOverlaySparkline(overlay: NonNullable<AccountDetail["liveBenchmarkOverlay"]>): string {
  if (overlay.points.length < 2) {
    return `<div class="muted">Benchmark overlay unavailable.</div>`;
  }

  const values = overlay.points.flatMap((item) => [item.accountEquity, item.benchmarkEquity]);
  const minEquity = Math.min(...values);
  const maxEquity = Math.max(...values);
  const spread = Math.max(maxEquity - minEquity, 1);
  const width = 320;
  const height = 96;
  const pad = 8;
  const pointFor = (value: number, index: number): string => {
    const x = pad + ((width - (pad * 2)) * index) / Math.max(overlay.points.length - 1, 1);
    const y = height - pad - (((value - minEquity) / spread) * (height - (pad * 2)));
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  };
  const accountPoints = overlay.points
    .map((item, index) => pointFor(item.accountEquity, index))
    .join(" ");
  const benchmarkPoints = overlay.points
    .map((item, index) => pointFor(item.benchmarkEquity, index))
    .join(" ");

  return `
    <div class="bt-equity-curve">
      <div class="row slim">
        <strong>Live vs ${esc(overlay.benchmark)}</strong>
        <span>Account ${overlay.accountReturnPct.toFixed(2)}% | Benchmark ${overlay.benchmarkReturnPct.toFixed(2)}% | Alpha ${overlay.alphaPct.toFixed(2)}%</span>
      </div>
      <div class="row slim">
        <span>Account line</span>
        <span style="color:#6b7280">Benchmark line</span>
      </div>
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Live vs ${esc(overlay.benchmark)}">
        <polyline fill="none" stroke="currentColor" stroke-width="2" points="${accountPoints}" />
        <polyline fill="none" stroke="#6b7280" stroke-width="2" stroke-dasharray="4 3" points="${benchmarkPoints}" />
      </svg>
    </div>
  `;
}

export function renderSnapshotsSection(
  detail: AccountDetail,
  activeSection: DetailSectionName,
  snapRows: string,
): string {
  return `
    <article class="detail-section-panel" data-detail-panel="snapshots" ${activeSection === "snapshots" ? "" : "hidden"}>
      <h4>Equity Snapshots</h4>
      ${detail.liveBenchmarkOverlay ? renderBenchmarkOverlaySparkline(detail.liveBenchmarkOverlay) : ""}
      ${renderEquitySparkline(detail.snapshots, { title: "Live Equity Curve" })}
      <table>
        <thead><tr><th>Time</th><th>Equity</th><th>Cash</th><th>Market Value</th></tr></thead>
        <tbody>${snapRows || `<tr><td colspan="4">No snapshots yet.</td></tr>`}</tbody>
      </table>
    </article>
  `;
}
