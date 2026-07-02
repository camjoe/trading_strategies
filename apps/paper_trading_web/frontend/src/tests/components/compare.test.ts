import { describe, expect, it } from "vitest";

import { renderComparisonTable } from "../../features/compare";
import type { AccountComparisonRow } from "../../types/compare";

function makeRow(overrides: Partial<AccountComparisonRow> = {}): AccountComparisonRow {
  return {
    name: "acct_compare",
    displayName: "Compare Account",
    strategy: "trend",
    benchmark: "SPY",
    equity: 1100,
    initialCash: 1000,
    totalChange: 100,
    totalChangePct: 10,
    liveBenchmarkReturnPct: 6,
    liveAlphaPct: 4,
    latestBacktest: null,
    evaluation: {
      blendedScore: 7.25,
      overallConfidence: 0.82,
      backtestConfidence: 0.9,
      paperLiveConfidence: 0.74,
      dataGaps: [],
    },
    ...overrides,
  };
}

describe("renderComparisonTable", () => {
  it("renders evaluation score, confidence, and no-gap status", () => {
    const html = renderComparisonTable([makeRow()]);

    expect(html).toContain("Score +7.25%");
    expect(html).toContain("Overall 0.82");
    expect(html).toContain("Backtest 0.90");
    expect(html).toContain("Paper/live 0.74");
    expect(html).toContain("No gaps");
  });

  it("renders missing blended score and data gap count", () => {
    const html = renderComparisonTable([
      makeRow({
        evaluation: {
          blendedScore: null,
          overallConfidence: 0,
          backtestConfidence: 0,
          paperLiveConfidence: 0,
          dataGaps: ["missing_backtest_evidence", "missing_paper_live_evidence"],
        },
      }),
    ]);

    expect(html).toContain("Score n/a");
    expect(html).toContain("2 gaps");
    expect(html).toContain("missing_backtest_evidence, missing_paper_live_evidence");
  });
});
