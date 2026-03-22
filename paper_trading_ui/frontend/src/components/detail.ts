import { currency, esc } from "../lib/format";
import type { AccountDetail } from "../types";

export interface DetailRenderOptions {
  tradePage?: number;
  tradePageSize?: number;
}

export function renderDetail(detail: AccountDetail, options: DetailRenderOptions = {}): string {
  const tradePageSize = Math.max(1, options.tradePageSize ?? 20);
  const totalTrades = detail.trades.length;
  const totalTradePages = Math.max(1, Math.ceil(totalTrades / tradePageSize));
  const tradePage = Math.min(Math.max(1, options.tradePage ?? 1), totalTradePages);
  const viewedStart = totalTrades === 0 ? 0 : (tradePage - 1) * tradePageSize + 1;
  const viewedEnd = totalTrades === 0 ? 0 : Math.min(tradePage * tradePageSize, totalTrades);

  const snapRows = detail.snapshots
    .slice(0, 25)
    .map(
      (s) => `
      <tr>
        <td>${new Date(s.time).toLocaleString()}</td>
        <td>${currency.format(s.equity)}</td>
        <td>${currency.format(s.cash)}</td>
        <td>${currency.format(s.marketValue)}</td>
      </tr>
    `,
    )
    .join("");

  const tradeStart = Math.max(0, totalTrades - tradePage * tradePageSize);
  const tradeEnd = totalTrades - (tradePage - 1) * tradePageSize;

  const tradeRows = detail.trades
    .slice(tradeStart, tradeEnd)
    .reverse()
    .map(
      (t) => `
      <tr>
        <td>${new Date(t.tradeTime).toLocaleString()}</td>
        <td>${esc(t.ticker)}</td>
        <td class="${t.side === "buy" ? "up" : "down"}">${esc(t.side)}</td>
        <td>${t.qty.toFixed(4)}</td>
        <td>${currency.format(t.price)}</td>
        <td>${currency.format(t.fee)}</td>
      </tr>
    `,
    )
    .join("");

  const latestBacktest = detail.latestBacktest
    ? `
      <div class="bt-result">
        <div><strong>Latest Backtest Run ${detail.latestBacktest.runId}</strong> ${esc(detail.latestBacktest.runName ?? "(unnamed)")}</div>
        <div>Range: ${esc(detail.latestBacktest.startDate)}..${esc(detail.latestBacktest.endDate)} | Created: ${new Date(detail.latestBacktest.createdAt).toLocaleString()}</div>
        <div>Slippage: ${detail.latestBacktest.slippageBps.toFixed(2)} bps | Fee: ${currency.format(detail.latestBacktest.feePerTrade)}</div>
        <button id="openLatestBacktestReportBtn" data-run-id="${detail.latestBacktest.runId}" type="button">Open Report</button>
      </div>
    `
    : `<div class="empty">No backtest run found for this account yet.</div>`;

  return `
    <div class="detail-head">
      <div>
        <h3>${esc(detail.account.displayName)}</h3>
        <p>${esc(detail.account.name)} | ${esc(detail.account.strategy)} | ${esc(detail.account.benchmark)}</p>
      </div>
      <button id="snapshotOneBtn" data-account="${esc(detail.account.name)}">Snapshot This Account</button>
    </div>

    <article>
      <h4>Latest Backtest</h4>
      ${latestBacktest}
    </article>

    <div class="detail-grid">
      <article>
        <h4>Equity Snapshots</h4>
        <table>
          <thead><tr><th>Time</th><th>Equity</th><th>Cash</th><th>Market Value</th></tr></thead>
          <tbody>${snapRows || `<tr><td colspan="4">No snapshots yet.</td></tr>`}</tbody>
        </table>
      </article>

      <article>
        <h4>Recent Trades</h4>
        <div class="table-pagination">
          <button id="recentTradesPrevBtn" type="button" ${tradePage <= 1 ? "disabled" : ""}>Newer</button>
          <span>${viewedStart} to ${viewedEnd} of ${totalTrades}</span>
          <button id="recentTradesNextBtn" type="button" ${tradePage >= totalTradePages ? "disabled" : ""}>Older</button>
        </div>
        <table>
          <thead><tr><th>Time</th><th>Ticker</th><th>Side</th><th>Qty</th><th>Price</th><th>Fee</th></tr></thead>
          <tbody>${tradeRows || `<tr><td colspan="6">No trades yet.</td></tr>`}</tbody>
        </table>
      </article>
    </div>
  `;
}
