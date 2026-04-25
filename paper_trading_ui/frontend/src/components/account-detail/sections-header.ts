import { currency, esc } from "../../lib/format";
import type { AccountDetail } from "../../types/accounts";
import type { DetailSectionName } from "./types";

export function renderDetailHeader(
  detail: AccountDetail,
  options: {
    benchmarkSummary: string;
    showAddTrade: boolean;
  },
): string {
  const { benchmarkSummary, showAddTrade } = options;
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
      ${showAddTrade ? `<div class="detail-head-actions">
        <button id="addTradeBtn" type="button">+ Add Trade</button>
      </div>` : ""}
    </div>
  `;
}

export function renderSectionTabs(
  activeSection: DetailSectionName,
  options: { showActions: boolean; accountName: string },
): string {
  const { showActions, accountName } = options;
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
      ${showActions ? `<span class="detail-section-tabs-spacer"></span>
        <div class="detail-section-tab-actions">
          <button id="openConfigBtn" class="icon-button" type="button" aria-label="Edit configuration" data-tooltip="Edit config">
            <span class="button-icon" aria-hidden="true">✎</span>
          </button>
          <button id="snapshotOneBtn" class="icon-button" type="button" data-account="${esc(accountName)}" aria-label="Snapshot this account" data-tooltip="Snapshot account">
            <svg class="button-icon-svg" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 8.5A2.5 2.5 0 0 1 6.5 6h1.9a1.5 1.5 0 0 0 1.06-.44l.5-.5A1.5 1.5 0 0 1 11.02 4.5h1.96a1.5 1.5 0 0 1 1.06.44l.5.5A1.5 1.5 0 0 0 15.6 6h1.9A2.5 2.5 0 0 1 20 8.5v7A2.5 2.5 0 0 1 17.5 18h-11A2.5 2.5 0 0 1 4 15.5z"/>
              <circle cx="12" cy="12" r="3.25"/>
            </svg>
          </button>
        </div>` : ""}
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
