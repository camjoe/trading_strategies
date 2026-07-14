import { find } from "../lib/dom";
import { currency, esc } from "../lib/format";
import { getJson } from "../lib/http";
import type {
  PortfolioConcentration,
  PortfolioExposure,
  PortfolioRollupResponse,
} from "../types/portfolio";

export interface PortfolioFeature {
  wireActions: () => void;
  loadRollup: () => Promise<void>;
}

/** Unsigned percentage share (portfolioPct is 0-100, never negative). */
function share(v: number): string {
  return `${v.toFixed(2)}%`;
}

export function renderExposureTable(exposure: PortfolioExposure): string {
  if (!exposure.accounts.length) {
    return `<div class="empty">No accounts found.</div>`;
  }

  const body = exposure.accounts
    .map((row) => {
      const hasSnapshot = row.snapshotTime !== null;
      return `
        <tr>
          <td><code>${esc(row.accountName)}</code></td>
          <td>${hasSnapshot ? esc(row.snapshotTime ?? "") : "no snapshots yet"}</td>
          <td>${row.equity === null ? "n/a" : currency.format(row.equity)}</td>
          <td>${row.cash === null ? "n/a" : currency.format(row.cash)}</td>
          <td>${row.marketValue === null ? "n/a" : currency.format(row.marketValue)}</td>
          <td>${row.positionCount}</td>
        </tr>
      `;
    })
    .join("");

  return `
    <div class="portfolio-table-wrap">
      <table class="portfolio-table">
        <thead>
          <tr>
            <th>Account</th>
            <th>Latest Snapshot</th>
            <th>Equity</th>
            <th>Cash</th>
            <th>Market Value</th>
            <th>Positions</th>
          </tr>
        </thead>
        <tbody>${body}</tbody>
        <tfoot>
          <tr>
            <td>Totals (${exposure.accountsWithSnapshots} of ${exposure.accountCount} with snapshots)</td>
            <td></td>
            <td>${currency.format(exposure.totalEquity)}</td>
            <td>${currency.format(exposure.totalCash)}</td>
            <td>${currency.format(exposure.totalMarketValue)}</td>
            <td></td>
          </tr>
        </tfoot>
      </table>
    </div>
  `;
}

export function renderConcentrationTable(concentration: PortfolioConcentration): string {
  if (!concentration.symbols.length) {
    return `<div class="empty">No open positions found.</div>`;
  }

  const body = concentration.symbols
    .map((row) => {
      const overlap = row.accountCount > 1;
      return `
        <tr${overlap ? ` class="portfolio-overlap"` : ""}>
          <td><code>${esc(row.symbol)}</code></td>
          <td>${esc(row.sector)}</td>
          <td>${currency.format(row.marketValue)}</td>
          <td>${share(row.portfolioPct)}</td>
          <td>${row.accountCount}</td>
          <td>${esc(row.accountNames.join(", "))}</td>
        </tr>
      `;
    })
    .join("");

  return `
    <div class="portfolio-table-wrap">
      <table class="portfolio-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Sector</th>
            <th>Market Value</th>
            <th>Share</th>
            <th>Accounts</th>
            <th>Held In</th>
          </tr>
        </thead>
        <tbody>${body}</tbody>
        <tfoot>
          <tr>
            <td>Total</td>
            <td></td>
            <td>${currency.format(concentration.totalMarketValue)}</td>
            <td></td>
            <td></td>
            <td></td>
          </tr>
        </tfoot>
      </table>
    </div>
  `;
}

export function renderSectorTable(concentration: PortfolioConcentration): string {
  if (!concentration.sectors.length) {
    return `<div class="empty">No open positions found.</div>`;
  }

  const body = concentration.sectors
    .map(
      (row) => `
        <tr>
          <td>${esc(row.sector)}</td>
          <td>${currency.format(row.marketValue)}</td>
          <td>${share(row.portfolioPct)}</td>
          <td>${row.symbolCount}</td>
        </tr>
      `,
    )
    .join("");

  return `
    <div class="portfolio-table-wrap">
      <table class="portfolio-table">
        <thead>
          <tr>
            <th>Sector</th>
            <th>Market Value</th>
            <th>Share</th>
            <th>Symbols</th>
          </tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
}

export function createPortfolioFeature(): PortfolioFeature {
  async function loadRollup(): Promise<void> {
    const exposureTarget = find<HTMLDivElement>("#portfolioExposure");
    const concentrationTarget = find<HTMLDivElement>("#portfolioConcentration");
    const sectorsTarget = find<HTMLDivElement>("#portfolioSectors");
    if (!exposureTarget || !concentrationTarget || !sectorsTarget) return;

    exposureTarget.innerHTML = `<div class="empty">Loading portfolio rollup...</div>`;
    concentrationTarget.innerHTML = `<div class="empty">Loading portfolio rollup...</div>`;
    sectorsTarget.innerHTML = `<div class="empty">Loading portfolio rollup...</div>`;

    try {
      const data = await getJson<PortfolioRollupResponse>("/api/portfolio/rollup");
      exposureTarget.innerHTML = renderExposureTable(data.exposure);
      concentrationTarget.innerHTML = renderConcentrationTable(data.concentration);
      sectorsTarget.innerHTML = renderSectorTable(data.concentration);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load portfolio rollup.";
      exposureTarget.innerHTML = `<div class="error">${esc(message)}</div>`;
      concentrationTarget.innerHTML = `<div class="error">${esc(message)}</div>`;
      sectorsTarget.innerHTML = `<div class="error">${esc(message)}</div>`;
    }
  }

  function wireActions(): void {
    find<HTMLButtonElement>("#refreshPortfolioBtn")?.addEventListener("click", () => {
      void loadRollup();
    });
  }

  return {
    wireActions,
    loadRollup,
  };
}
