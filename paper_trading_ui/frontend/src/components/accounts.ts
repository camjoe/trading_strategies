import { currency, esc, num, pct } from "../lib/format";
import type { AccountListItem } from "../types";

export interface AccountCardOptions {
  selected?: boolean;
}

export function accountCard(a: AccountListItem, options: AccountCardOptions = {}): string {
  const pnlClass = a.totalChange >= 0 ? "up" : "down";
  const latestSnapshot = a.latestSnapshotTime ? new Date(a.latestSnapshotTime).toLocaleString() : "none";
  const snapshotChange = a.changeSinceLastSnapshot === null ? "n/a" : num(a.changeSinceLastSnapshot);
  const selectedClass = options.selected ? " active" : "";
  const selectedAria = options.selected ? ` aria-current="true"` : "";

  return `
    <button class="account-card${selectedClass}" data-account="${esc(a.name)}"${selectedAria}>
      <div class="row top">
        <strong>${esc(a.displayName)}</strong>
        <span class="chip">${esc(a.strategy)}</span>
      </div>
      <div class="row slim">Name: ${esc(a.name)} | Benchmark: ${esc(a.benchmark)}</div>
      <div class="row">
        <span>Equity</span>
        <strong>${currency.format(a.equity)}</strong>
      </div>
      <div class="row ${pnlClass}">
        <span>Total Change</span>
        <strong>${num(a.totalChange)} (${pct(a.totalChangePct)})</strong>
      </div>
      <div class="row slim">
        <span>Since Last Snapshot: ${snapshotChange}</span>
      </div>
      <div class="row slim">
        <span>Last Snapshot: ${latestSnapshot}</span>
      </div>
    </button>
  `;
}
