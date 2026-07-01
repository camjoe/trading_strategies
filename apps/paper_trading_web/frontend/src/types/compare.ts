import type { LatestBacktestMetrics } from "./backtesting";

export type AccountComparisonEvaluation = {
  blendedScore: number | null;
  overallConfidence: number;
  backtestConfidence: number;
  paperLiveConfidence: number;
  dataGaps: string[];
};

export type AccountComparisonRow = {
  name: string;
  displayName: string;
  strategy: string;
  benchmark: string;
  equity: number;
  initialCash: number;
  totalChange: number;
  totalChangePct: number;
  liveBenchmarkReturnPct: number | null;
  liveAlphaPct: number | null;
  latestBacktest: LatestBacktestMetrics | null;
  evaluation: AccountComparisonEvaluation;
};
