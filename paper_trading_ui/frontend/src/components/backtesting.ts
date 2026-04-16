import { currency, esc, pct } from "../lib/format";
import type { BacktestReport, BacktestRunResult, BacktestRunSummary, WalkForwardResult } from "../types";

export function warningListHtml(warnings: string[]): string {
  if (!warnings.length) {
    return `<div class="empty">No financial-model warnings for the current configuration.</div>`;
  }
  return `<ul>${warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>`;
}

function metricCell(label: string, value: string): string {
  return `
    <div class="analysis-stat">
      <span class="label">${esc(label)}</span>
      <span>${value}</span>
    </div>
  `;
}

function metricPct(value: number | null | undefined): string {
  return value == null ? "—" : pct(value);
}

function metricNum(value: number | null | undefined, digits = 2): string {
  return value == null ? "—" : value.toFixed(digits);
}

function renderBacktestMetricGrid(metrics: {
  sharpeRatio?: number | null;
  sortinoRatio?: number | null;
  calmarRatio?: number | null;
  winRatePct?: number | null;
  profitFactor?: number | null;
  avgTradeReturnPct?: number | null;
}): string {
  return `
    <div class="analysis-summary">
      ${metricCell("Sharpe", metricNum(metrics.sharpeRatio))}
      ${metricCell("Sortino", metricNum(metrics.sortinoRatio))}
      ${metricCell("Calmar", metricNum(metrics.calmarRatio))}
      ${metricCell("Win Rate", metricPct(metrics.winRatePct))}
      ${metricCell("Profit Factor", metricNum(metrics.profitFactor))}
      ${metricCell("Avg Trade Return", metricPct(metrics.avgTradeReturnPct))}
    </div>
  `;
}

function renderEquityCurve(
  snapshots: Array<{ snapshot_time: string; equity: number }> | undefined,
  options: { title: string },
): string {
  const { title } = options;
  if (!snapshots || snapshots.length < 2) {
    return `<div class="muted">${esc(title)} unavailable.</div>`;
  }

  const equities = snapshots.map((item) => item.equity);
  const minEquity = Math.min(...equities);
  const maxEquity = Math.max(...equities);
  const width = 320;
  const height = 96;
  const pad = 8;
  const spread = Math.max(maxEquity - minEquity, 1);
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

export function renderBacktestRunResult(result: BacktestRunResult): string {
  const benchmarkLine =
    result.benchmarkReturnPct === null || result.alphaPct === null
      ? "Benchmark: unavailable"
      : `Benchmark ${pct(result.benchmarkReturnPct)} | Alpha ${pct(result.alphaPct)}`;

  return `
    <div class="bt-result">
      <div><strong>Run ${result.runId}</strong> | ${esc(result.accountName)} | ${esc(result.startDate)}..${esc(result.endDate)}</div>
      <div>Trades: ${result.tradeCount} | End Equity: ${currency.format(result.endingEquity)} | Return: ${pct(result.totalReturnPct)} | Max DD: ${pct(result.maxDrawdownPct)}</div>
      <div>${benchmarkLine}</div>
      ${renderBacktestMetricGrid(result)}
      <div class="bt-warning">${warningListHtml(result.warnings)}</div>
    </div>
  `;
}

export function renderWalkForwardResult(result: WalkForwardResult): string {
  const runIds = result.runIds.length ? result.runIds.join(", ") : "none";
  return `
    <div class="bt-result">
      <div><strong>${esc(result.accountName)}</strong> | ${esc(result.startDate)}..${esc(result.endDate)} | Windows: ${result.windowCount}</div>
      <div>Avg ${pct(result.averageReturnPct)} | Median ${pct(result.medianReturnPct)} | Best ${pct(result.bestReturnPct)} | Worst ${pct(result.worstReturnPct)}</div>
      <div>Run IDs: ${esc(runIds)}</div>
    </div>
  `;
}

export function renderBacktestRunCard(run: BacktestRunSummary): string {
  const created = new Date(run.createdAt).toLocaleString();
  return `
    <button class="bt-run-item" data-run-id="${run.runId}">
      <div class="row top">
        <strong>#${run.runId} ${esc(run.runName ?? "(unnamed)")}</strong>
        <span class="chip">${esc(run.accountName)}</span>
      </div>
      <div class="row slim">${esc(run.strategy)} | ${esc(run.startDate)}..${esc(run.endDate)}</div>
      <div class="row slim">Created: ${created}</div>
    </button>
  `;
}

export function renderBacktestReport(report: BacktestReport): string {
  return `
    <div class="bt-result">
      <div><strong>Run ${report.run_id}</strong> ${esc(report.run_name ?? "(unnamed)")} | ${esc(report.account_name)} | ${esc(report.strategy)}</div>
      <div>Range: ${esc(report.start_date)}..${esc(report.end_date)} | Benchmark: ${esc(report.benchmark_ticker)}</div>
      <div>Start: ${currency.format(report.starting_equity)} | End: ${currency.format(report.ending_equity)} | Return: ${pct(report.total_return_pct)} | Max DD: ${pct(report.max_drawdown_pct)}</div>
      <div>Trades: ${report.trade_count} | Slippage: ${report.slippage_bps.toFixed(2)} bps | Fee: ${currency.format(report.fee_per_trade)} | Benchmark: ${metricPct(report.benchmark_return_pct)} | Alpha: ${metricPct(report.alpha_pct)}</div>
      ${renderBacktestMetricGrid({
        sharpeRatio: report.sharpe_ratio,
        sortinoRatio: report.sortino_ratio,
        calmarRatio: report.calmar_ratio,
        winRatePct: report.win_rate_pct,
        profitFactor: report.profit_factor,
        avgTradeReturnPct: report.avg_trade_return_pct,
      })}
      ${renderEquityCurve(report.snapshots, { title: "Equity Curve" })}
      <div class="bt-warning">${warningListHtml(report.warnings ?? [])}</div>
    </div>
  `;
}
