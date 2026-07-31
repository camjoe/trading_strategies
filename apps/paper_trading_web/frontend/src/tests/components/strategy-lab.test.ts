import { describe, expect, it } from "vitest";

import type { ExperimentDetail, Trial } from "../../components/strategy-lab";
import {
  SWEEP_WARNING_SIMULATIONS,
  estimateSweep,
  rankedTrials,
  renderOptimizationDetail,
  renderTrialsTable,
  sweepConfirmMessage,
} from "../../components/strategy-lab";

function trial(overrides: Partial<Trial> = {}): Trial {
  return {
    candidateIndex: 0,
    params: { fast_window: 5 },
    objectiveValue: 1,
    annualizedReturnPct: 1,
    maxDrawdownPct: -5,
    tradeCount: 9,
    eligible: true,
    rejectionReason: null,
    selected: false,
    ...overrides,
  };
}

const detail: ExperimentDetail = {
  experiment: {
    id: 7,
    accountName: "audit_acct",
    primitive: "trend",
    winnerParams: { fast_window: 10 },
    windowCount: 1,
    oosMeanWinnerReturnPct: 4,
    oosMeanBaselineReturnPct: 1,
    oosWindowsBeatBaseline: 1,
    holdoutWinnerReturnPct: 6,
    holdoutBaselineReturnPct: 2,
    promotedStrategyId: null,
    createdAt: "2026-04-01T00:00:00Z",
    status: "completed",
    failureStage: null,
    failureMessage: null,
    startDate: "2025-01-01",
    endDate: "2026-03-31",
    trainMonths: 12,
    testMonths: 1,
    stepMonths: 1,
    holdoutMonths: 6,
    warmupMonths: 6,
    candidateBudget: 8,
    holdoutRunId: 99,
  },
  gate: { passed: true, reasons: [] },
  windows: [
    {
      windowIndex: 1,
      trainStart: "2025-01-01",
      trainEnd: "2025-12-31",
      testStart: "2026-01-01",
      testEnd: "2026-01-31",
      oosRunId: 42,
      trials: [
        trial({ candidateIndex: 0, objectiveValue: 0.5 }),
        trial({
          candidateIndex: 1,
          objectiveValue: 2.5,
          selected: true,
          params: { fast_window: 10 },
        }),
        trial({
          candidateIndex: 2,
          objectiveValue: null,
          eligible: false,
          rejectionReason: "too_few_trades (1 < 3)",
        }),
      ],
    },
  ],
  compoundedOos: {
    compoundedReturnPct: 12.5,
    hasGaps: false,
    points: [
      {
        windowIndex: 1,
        testStart: "2026-01-01",
        testEnd: "2026-01-31",
        periodReturnPct: 12.5,
        cumulativeReturnPct: 12.5,
        gapBefore: false,
      },
    ],
  },
  manifest: null,
};

describe("rankedTrials", () => {
  it("orders eligible candidates by objective and keeps rejected ones last", () => {
    const ordered = rankedTrials(detail.windows[0].trials);
    expect(ordered.map(item => item.candidateIndex)).toEqual([1, 0, 2]);
  });

  it("does not mutate the caller's canonical search order", () => {
    const trials = detail.windows[0].trials;
    rankedTrials(trials);
    expect(trials.map(item => item.candidateIndex)).toEqual([0, 1, 2]);
  });
});

describe("renderTrialsTable", () => {
  it("shows every evaluated candidate with its rejection reason", () => {
    const html = renderTrialsTable(detail.windows[0].trials);
    // The rejected candidate is part of the multiple-testing record, not noise to hide.
    expect(html).toContain("too_few_trades (1 &lt; 3)");
    expect(html).toContain("winner");
    expect((html.match(/<tr>/g) ?? []).length).toBe(4); // header + 3 candidates
  });

  it("reports an empty window instead of an empty table", () => {
    expect(renderTrialsTable([])).toContain("No candidate trials persisted");
  });
});

describe("renderOptimizationDetail", () => {
  it("renders the gate verdict, windows, and compounded series", () => {
    const html = renderOptimizationDetail(detail);
    expect(html).toContain("gate: PASS");
    expect(html).toContain("Window 1");
    expect(html).toContain("OOS run #42");
    expect(html).toContain("Compounded OOS return");
    expect(html).toContain("No provenance manifest stored");
  });

  it("lists every gate failure reason rather than only the first", () => {
    const html = renderOptimizationDetail({
      ...detail,
      gate: {
        passed: false,
        reasons: [
          "no holdout evidence",
          "OOS mean return did not beat baseline",
        ],
      },
    });
    expect(html).toContain("gate: FAIL");
    expect(html).toContain("no holdout evidence");
    expect(html).toContain("OOS mean return did not beat baseline");
  });

  it("shows the failure stage and message for a failed experiment and no audit tree", () => {
    const html = renderOptimizationDetail({
      ...detail,
      experiment: {
        ...detail.experiment,
        status: "failed",
        failureStage: "holdout",
        failureMessage: "boom",
      },
    });
    expect(html).toContain("failed");
    expect(html).toContain("holdout");
    expect(html).toContain("boom");
    expect(html).not.toContain("Window 1");
  });
});

describe("estimateSweep", () => {
  it("counts windows and simulations, not just candidates", () => {
    // 24 months, 6 held out, 12 trained on -> 6 monthly windows.
    const estimate = estimateSweep({ candidates: 4, lookbackMonths: 24, holdoutMonths: 6 });
    expect(estimate.windows).toBe(6);
    // 4 candidates x 6 windows, plus an OOS and a baseline run per window, plus the holdout pair.
    expect(estimate.simulations).toBe(38);
    expect(estimate.overWarningThreshold).toBe(false);
  });

  it("flags a grid whose real cost is hidden by a modest candidate count", () => {
    // 32 candidates looks small; 30 monthly windows turns it into ~1,000 backtests.
    const estimate = estimateSweep({ candidates: 32, lookbackMonths: 48, holdoutMonths: 6 });
    expect(estimate.windows).toBe(30);
    expect(estimate.simulations).toBeGreaterThan(SWEEP_WARNING_SIMULATIONS);
    expect(estimate.overWarningThreshold).toBe(true);
  });

  it("does not warn on a sweep the engine now finishes quickly", () => {
    const estimate = estimateSweep({ candidates: 8, lookbackMonths: 48, holdoutMonths: 6 });
    expect(estimate.simulations).toBeLessThan(SWEEP_WARNING_SIMULATIONS);
    expect(estimate.overWarningThreshold).toBe(false);
  });

  it("reports no windows when the holdout leaves no room to train", () => {
    const estimate = estimateSweep({ candidates: 4, lookbackMonths: 12, holdoutMonths: 6 });
    expect(estimate.windows).toBe(0);
    expect(estimate.simulations).toBe(0);
  });
});

describe("sweepConfirmMessage", () => {
  it("states candidates, windows, and the backtest count", () => {
    const message = sweepConfirmMessage(
      estimateSweep({ candidates: 4, lookbackMonths: 24, holdoutMonths: 6 }),
    );
    expect(message).toContain("4 candidates");
    expect(message).toContain("6 windows");
    expect(message).toContain("38 backtests");
    expect(message).not.toContain("long synchronous run");
  });

  it("warns that the page stays open when the sweep is large", () => {
    const message = sweepConfirmMessage(
      estimateSweep({ candidates: 32, lookbackMonths: 48, holdoutMonths: 6 }),
    );
    expect(message).toContain("long synchronous run");
  });

  it("says so when the geometry yields no windows at all", () => {
    const message = sweepConfirmMessage(
      estimateSweep({ candidates: 4, lookbackMonths: 12, holdoutMonths: 6 }),
    );
    expect(message).toContain("no room for a training window");
  });
});
