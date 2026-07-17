import { describe, expect, it } from "vitest";

import {
  renderConcentrationTable,
  renderExposureTable,
  renderSectorTable,
} from "../../features/portfolio";
import type { PortfolioConcentration, PortfolioExposure } from "../../types/portfolio";

function makeExposure(overrides: Partial<PortfolioExposure> = {}): PortfolioExposure {
  return {
    accounts: [
      {
        accountId: 1,
        accountName: "alpha",
        snapshotTime: "2026-07-09T00:00:00Z",
        cash: 750,
        marketValue: 250,
        equity: 1000,
        positionCount: 2,
      },
      {
        accountId: 2,
        accountName: "beta",
        snapshotTime: null,
        cash: null,
        marketValue: null,
        equity: null,
        positionCount: 0,
      },
    ],
    accountCount: 2,
    accountsWithSnapshots: 1,
    totalCash: 750,
    totalMarketValue: 250,
    totalEquity: 1000,
    ...overrides,
  };
}

function makeConcentration(overrides: Partial<PortfolioConcentration> = {}): PortfolioConcentration {
  return {
    symbols: [
      {
        symbol: "AAPL",
        sector: "tech",
        marketValue: 600,
        portfolioPct: 60,
        accountCount: 2,
        accountNames: ["alpha", "beta"],
      },
      {
        symbol: "XLE",
        sector: "uncategorized",
        marketValue: 400,
        portfolioPct: 40,
        accountCount: 1,
        accountNames: ["alpha"],
      },
    ],
    sectors: [
      { sector: "tech", marketValue: 600, portfolioPct: 60, symbolCount: 1 },
      { sector: "uncategorized", marketValue: 400, portfolioPct: 40, symbolCount: 1 },
    ],
    totalMarketValue: 1000,
    ...overrides,
  };
}

describe("renderExposureTable", () => {
  it("renders snapshot balances, no-snapshot placeholder, and totals", () => {
    const html = renderExposureTable(makeExposure());

    expect(html).toContain("alpha");
    expect(html).toContain("$1,000.00");
    expect(html).toContain("no snapshots yet");
    expect(html).toContain("n/a");
    expect(html).toContain("Totals (1 of 2 with snapshots)");
  });

  it("renders empty state without accounts", () => {
    const html = renderExposureTable(makeExposure({ accounts: [], accountCount: 0, accountsWithSnapshots: 0 }));

    expect(html).toContain("No accounts found.");
  });
});

describe("renderConcentrationTable", () => {
  it("renders share, holders, and marks cross-account overlap rows", () => {
    const html = renderConcentrationTable(makeConcentration());

    expect(html).toContain("AAPL");
    expect(html).toContain("60.00%");
    expect(html).toContain("alpha, beta");
    expect(html).toContain("portfolio-overlap");
    expect(html).toContain("$1,000.00");
  });

  it("renders empty state without positions", () => {
    const html = renderConcentrationTable(makeConcentration({ symbols: [], sectors: [], totalMarketValue: 0 }));

    expect(html).toContain("No open positions found.");
  });
});

describe("renderSectorTable", () => {
  it("renders sector shares and symbol counts", () => {
    const html = renderSectorTable(makeConcentration());

    expect(html).toContain("tech");
    expect(html).toContain("uncategorized");
    expect(html).toContain("40.00%");
  });
});
