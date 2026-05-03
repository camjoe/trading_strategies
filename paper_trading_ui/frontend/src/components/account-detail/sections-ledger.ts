import { currency, esc } from "../../lib/format";
import type { AccountDetail } from "../../types/accounts";
import type { DetailSectionName } from "./types";

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
