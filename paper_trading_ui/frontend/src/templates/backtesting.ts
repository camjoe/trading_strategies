import { currency, esc, pct } from "../lib/format";
import type { BacktestReport, BacktestRunResult, BacktestRunSummary, WalkForwardResult } from "../types";

export function warningListHtml(warnings: string[]): string {
  if (!warnings.length) {
    return `<div class="empty">No financial-model warnings for the current configuration.</div>`;
  }
  return `<ul>${warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>`;
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
  const warningItems = String(report.warnings || "")
    .split(" | ")
    .map((v) => v.trim())
    .filter((v) => v.length > 0);

  return `
    <div class="bt-result">
      <div><strong>Run ${report.run_id}</strong> ${esc(report.run_name ?? "(unnamed)")} | ${esc(report.account_name)} | ${esc(report.strategy)}</div>
      <div>Range: ${esc(report.start_date)}..${esc(report.end_date)} | Benchmark: ${esc(report.benchmark_ticker)}</div>
      <div>Start: ${currency.format(report.starting_equity)} | End: ${currency.format(report.ending_equity)} | Return: ${pct(report.total_return_pct)} | Max DD: ${pct(report.max_drawdown_pct)}</div>
      <div>Trades: ${report.trade_count} | Slippage: ${report.slippage_bps.toFixed(2)} bps | Fee: ${currency.format(report.fee_per_trade)}</div>
      <div class="bt-warning">${warningListHtml(warningItems)}</div>
    </div>
  `;
}
