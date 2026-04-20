import { currency, esc } from "../../lib/format";
import type { AccountAnalysis } from "../../types";

export function renderAnalysisPanel(analysis: AccountAnalysis): string {
  const signClass = (value: number) => (value >= 0 ? "up" : "down");
  const pct = (value: number | null) =>
    value == null ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;

  const benchmarkLine = analysis.benchmarkReturnPct != null
    ? `<span class="${signClass(analysis.benchmarkReturnPct)}">${pct(analysis.benchmarkReturnPct)}</span>`
    : `<span class="muted">—</span>`;

  const alphaLine = analysis.alphaPct != null
    ? `<span class="${signClass(analysis.alphaPct)}">${pct(analysis.alphaPct)} alpha</span>`
    : `<span class="muted">—</span>`;

  const positionRows = (positions: AccountAnalysis["topWinners"]) =>
    positions
      .map(
        (position) => `
        <tr>
          <td><strong>${esc(position.ticker)}</strong></td>
          <td>${currency.format(position.avgCost)}</td>
          <td>${position.marketPrice > 0 ? currency.format(position.marketPrice) : "—"}</td>
          <td class="${signClass(position.unrealizedPnl)}">${position.marketPrice > 0 ? currency.format(position.unrealizedPnl) : "—"}</td>
          <td class="${signClass(position.unrealizedPnlPct)}">${position.marketPrice > 0 ? pct(position.unrealizedPnlPct) : "—"}</td>
        </tr>`,
      )
      .join("");

  const notesList = analysis.improvementNotes
    .map((note) => `<li>${esc(note)}</li>`)
    .join("");

  return `
    <h4>Performance Analysis</h4>
    <div class="analysis-summary">
      <div class="analysis-stat">
        <span class="label">Account Return</span>
        <span class="${signClass(analysis.accountReturnPct)}">${pct(analysis.accountReturnPct)}</span>
      </div>
      <div class="analysis-stat">
        <span class="label">Benchmark (${analysis.benchmarkReturnPct != null ? (analysis.benchmarkTicker ?? "—") : "—"})</span>
        ${benchmarkLine}
      </div>
      <div class="analysis-stat">
        <span class="label">Alpha</span>
        ${alphaLine}
      </div>
      <div class="analysis-stat">
        <span class="label">Realized P&amp;L</span>
        <span class="${signClass(analysis.realizedPnl)}">${currency.format(analysis.realizedPnl)}</span>
      </div>
      <div class="analysis-stat">
        <span class="label">Unrealized P&amp;L</span>
        <span class="${signClass(analysis.unrealizedPnl)}">${currency.format(analysis.unrealizedPnl)}</span>
      </div>
    </div>

    <div class="analysis-tables">
      <div>
        <h5>Top Winners <span class="muted analysis-table-note">(open positions, unrealized)</span></h5>
        <table>
          <thead><tr><th>Ticker</th><th>Avg Cost</th><th>Price</th><th>Unr. P&amp;L</th><th>%</th></tr></thead>
          <tbody>${positionRows(analysis.topWinners) || `<tr><td colspan="5">None</td></tr>`}</tbody>
        </table>
      </div>
      <div>
        <h5>Top Losers <span class="muted analysis-table-note">(open positions, unrealized)</span></h5>
        <table>
          <thead><tr><th>Ticker</th><th>Avg Cost</th><th>Price</th><th>Unr. P&amp;L</th><th>%</th></tr></thead>
          <tbody>${positionRows(analysis.topLosers) || `<tr><td colspan="5">None</td></tr>`}</tbody>
        </table>
      </div>
    </div>

    ${notesList ? `<div class="analysis-notes"><h5>Improvement Notes</h5><ul>${notesList}</ul></div>` : ""}
  `;
}
