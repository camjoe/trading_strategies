import type { LatestBacktestMetrics } from "./backtesting";

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
};
