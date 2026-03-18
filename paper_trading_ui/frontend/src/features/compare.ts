import { find } from "../lib/dom";
import { currency, pct } from "../lib/format";
import { getJson } from "../lib/http";
import type { AccountComparisonRow } from "../types";

export interface CompareFeature {
  wireActions: () => void;
  loadComparison: () => Promise<void>;
}

function renderComparisonTable(rows: AccountComparisonRow[]): string {
  if (!rows.length) {
    return `<div class="empty">No accounts available to compare.</div>`;
  }

  const sorted = [...rows].sort((a, b) => b.totalChangePct - a.totalChangePct);
  const body = sorted
    .map((row) => {
      const bt = row.latestBacktest;
      return `
        <tr>
          <td>${row.displayName}</td>
          <td>${row.name}</td>
          <td>${row.strategy}</td>
          <td>${row.benchmark}</td>
          <td>${currency.format(row.initialCash)}</td>
          <td>${currency.format(row.equity)}</td>
          <td class="${row.totalChange >= 0 ? "up" : "down"}">${currency.format(row.totalChange)}</td>
          <td class="${row.totalChangePct >= 0 ? "up" : "down"}">${pct(row.totalChangePct)}</td>
          <td>${bt ? pct(bt.totalReturnPct) : "n/a"}</td>
          <td>${bt && bt.alphaPct !== null ? pct(bt.alphaPct) : "n/a"}</td>
          <td>${bt ? pct(bt.maxDrawdownPct) : "n/a"}</td>
          <td>${bt ? bt.endDate : "n/a"}</td>
        </tr>
      `;
    })
    .join("");

  return `
    <div class="compare-table-wrap">
      <table class="compare-table">
        <thead>
          <tr>
            <th>Display Name</th>
            <th>Account</th>
            <th>Strategy</th>
            <th>Benchmark</th>
            <th>Initial Cash</th>
            <th>Equity</th>
            <th>Total Change</th>
            <th>Total Return</th>
            <th>Latest Backtest Return</th>
            <th>Latest Alpha</th>
            <th>Latest Max DD</th>
            <th>Latest Backtest End</th>
          </tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
}

export function createCompareFeature(): CompareFeature {
  async function loadComparison(): Promise<void> {
    const target = find<HTMLDivElement>("#compareTable");
    if (!target) return;

    target.innerHTML = `<div class="empty">Loading comparison data...</div>`;
    try {
      const data = await getJson<{ accounts: AccountComparisonRow[] }>("/api/accounts/compare");
      target.innerHTML = renderComparisonTable(data.accounts);
    } catch (error) {
      target.innerHTML = `<div class="error">${error instanceof Error ? error.message : "Failed to load comparison."}</div>`;
    }
  }

  function wireActions(): void {
    const refreshBtn = find<HTMLButtonElement>("#refreshCompareBtn");
    refreshBtn?.addEventListener("click", () => {
      void loadComparison();
    });
  }

  return {
    wireActions,
    loadComparison,
  };
}
