import { find } from "../lib/dom";
import { currency, esc, pct } from "../lib/format";
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

function populateStrategyFilter(rows: AccountComparisonRow[]): void {
  const select = find<HTMLSelectElement>("#compare-strategy-filter");
  if (!select) return;

  const strategies = [...new Set(rows.map((r) => r.strategy))].sort();
  select.innerHTML =
    `<option value="">All strategies</option>` +
    strategies.map((s) => `<option value="${esc(s)}">${esc(s)}</option>`).join("");
}

export function createCompareFeature(): CompareFeature {
  let allRows: AccountComparisonRow[] = [];

  function applyFilter(): void {
    const target = find<HTMLDivElement>("#compareTable");
    const select = find<HTMLSelectElement>("#compare-strategy-filter");
    if (!target) return;

    const selected = select?.value ?? "";
    const visible = selected ? allRows.filter((r) => r.strategy === selected) : allRows;
    target.innerHTML = renderComparisonTable(visible);
  }

  async function loadComparison(): Promise<void> {
    const target = find<HTMLDivElement>("#compareTable");
    if (!target) return;

    target.innerHTML = `<div class="empty">Loading comparison data...</div>`;

    // Reset filter state on each reload
    const select = find<HTMLSelectElement>("#compare-strategy-filter");
    if (select) select.value = "";

    try {
      const data = await getJson<{ accounts: AccountComparisonRow[] }>("/api/accounts/compare");
      allRows = data.accounts;
      populateStrategyFilter(allRows);
      target.innerHTML = renderComparisonTable(allRows);
    } catch (error) {
      allRows = [];
      target.innerHTML = `<div class="error">${error instanceof Error ? error.message : "Failed to load comparison."}</div>`;
    }
  }

  function wireActions(): void {
    find<HTMLButtonElement>("#refreshCompareBtn")?.addEventListener("click", () => {
      void loadComparison();
    });

    find<HTMLSelectElement>("#compare-strategy-filter")?.addEventListener("change", () => {
      applyFilter();
    });
  }

  return {
    wireActions,
    loadComparison,
  };
}
