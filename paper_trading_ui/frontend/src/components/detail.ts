import { currency, esc } from "../lib/format";
import { renderAnalysisPanel } from "./account-detail/analysis";
import { renderConfigSection } from "./account-detail/config";
import {
  renderAddTradePanel,
  renderAnalysisSection,
  renderDetailHeader,
  renderPositionsSection,
  renderSectionTabs,
  renderSnapshotsSection,
  renderSummarySection,
  renderTradesSection,
} from "./account-detail/sections";
import type { AccountDetail } from "../types";

export interface DetailRenderOptions {
  tradePage?: number;
  tradePageSize?: number;
  activeSection?: "summary" | "analysis" | "positions" | "trades" | "snapshots" | "config";
  showActions?: boolean;
  showAddTrade?: boolean;
  showBacktest?: boolean;
}

function tradeTypeBadge(note: string | null): string {
  if (!note) return `<span class="chip chip--equity">equity</span>`;
  if (note.includes("instrument=option")) return `<span class="chip chip--option">option</span>`;
  if (note.includes("auto-daily")) return `<span class="chip chip--auto">auto</span>`;
  return `<span class="chip chip--manual">manual</span>`;
}

function metricValue(value: number | null | undefined, suffix = "", digits = 2): string {
  return value == null ? "—" : `${value.toFixed(digits)}${suffix}`;
}

export function renderDetail(detail: AccountDetail, options: DetailRenderOptions = {}): string {
  const tradePageSize = Math.max(1, options.tradePageSize ?? 20);
  const totalTrades = detail.trades.length;
  const totalTradePages = Math.max(1, Math.ceil(totalTrades / tradePageSize));
  const tradePage = Math.min(Math.max(1, options.tradePage ?? 1), totalTradePages);
  const showActions = options.showActions !== false;
  const showAddTrade = options.showAddTrade === true;
  const showBacktest = options.showBacktest !== false;
  const activeSection = options.activeSection ?? "summary";
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
  let previousDayKey = "";
  let dayBand = 0;

  const tradeRows = detail.trades
    .slice(tradeStart, tradeEnd)
    .reverse()
    .map((t) => {
      const tradeDate = new Date(t.tradeTime);
      const dayKey = `${tradeDate.getFullYear()}-${tradeDate.getMonth() + 1}-${tradeDate.getDate()}`;
      if (dayKey !== previousDayKey) {
        dayBand += 1;
        previousDayKey = dayKey;
      }
      const dayClass = dayBand % 2 === 0 ? " trade-row--alt-day" : "";

      return `
      <tr class="trade-row${dayClass}">
        <td>${tradeDate.toLocaleString()}</td>
        <td>${esc(t.ticker)}</td>
        <td class="${t.side === "buy" ? "up" : "down"}">${esc(t.side)}</td>
        <td>${tradeTypeBadge(t.note)}</td>
        <td>${t.qty.toFixed(2)}</td>
        <td>${currency.format(t.price)}</td>
        <td>${currency.format(t.qty * t.price)}</td>
      </tr>
    `;
    })
    .join("");

  const latestBacktest = detail.latestBacktest
    ? `
      <div class="bt-result">
        <div><strong>Latest Backtest Run ${detail.latestBacktest.runId}</strong> ${esc(detail.latestBacktest.runName ?? "(unnamed)")}</div>
        <div>Range: ${esc(detail.latestBacktest.startDate)}..${esc(detail.latestBacktest.endDate)} | Created: ${new Date(detail.latestBacktest.createdAt).toLocaleString()}</div>
        <div>Slippage: ${detail.latestBacktest.slippageBps.toFixed(2)} bps | Fee: ${currency.format(detail.latestBacktest.feePerTrade)}</div>
        ${detail.latestBacktestMetrics
          ? `<div class="analysis-summary">
              <div class="analysis-stat"><span class="label">Backtest Return</span><span>${metricValue(detail.latestBacktestMetrics.totalReturnPct, "%")}</span></div>
              <div class="analysis-stat"><span class="label">Max DD</span><span>${metricValue(detail.latestBacktestMetrics.maxDrawdownPct, "%")}</span></div>
              <div class="analysis-stat"><span class="label">Sharpe</span><span>${metricValue(detail.latestBacktestMetrics.sharpeRatio)}</span></div>
              <div class="analysis-stat"><span class="label">Win Rate</span><span>${metricValue(detail.latestBacktestMetrics.winRatePct, "%")}</span></div>
              <div class="analysis-stat"><span class="label">Profit Factor</span><span>${metricValue(detail.latestBacktestMetrics.profitFactor)}</span></div>
            </div>`
          : ""}
        <button id="openLatestBacktestReportBtn" data-run-id="${detail.latestBacktest.runId}" type="button">Open Report</button>
      </div>
    `
    : `<div class="empty">No backtest run found for this account yet.</div>`;
  const benchmarkSummary = detail.liveBenchmarkOverlay
    ? `<div class="analysis-summary">
         <div class="analysis-stat"><span class="label">Benchmark Return</span><span>${metricValue(detail.liveBenchmarkOverlay.benchmarkReturnPct, "%")}</span></div>
         <div class="analysis-stat"><span class="label">Live Alpha</span><span>${metricValue(detail.liveBenchmarkOverlay.alphaPct, "%")}</span></div>
         <div class="analysis-stat"><span class="label">Benchmark Equity</span><span>${currency.format(detail.liveBenchmarkOverlay.benchmarkEquity)}</span></div>
       </div>`
    : "";

  return `
    ${renderDetailHeader(detail, { benchmarkSummary, showActions, showAddTrade })}
    ${renderSectionTabs(activeSection)}
    ${renderAddTradePanel(showAddTrade)}
    ${renderSummarySection(activeSection, { showBacktest, latestBacktest })}
    ${renderAnalysisSection(activeSection)}
    ${renderPositionsSection(detail, activeSection)}
    ${renderTradesSection(tradeRows, {
      activeSection,
      tradePage,
      viewedStart,
      viewedEnd,
      totalTrades,
      totalTradePages,
    })}
    ${renderSnapshotsSection(detail, activeSection, snapRows)}
    ${renderConfigSection(detail, { activeSection, showActions })}
  `;
}

export { renderAnalysisPanel };
