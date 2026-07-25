import type { BacktestRunSummary, LatestBacktestMetrics } from "./backtesting";

export type AccountListItem = {
  name: string;
  displayName: string;
  strategy: string;
  instrumentMode: string;
  benchmark: string;
  equity: number;
  totalChange: number;
  totalChangePct: number;
  changeSinceLastSnapshot: number | null;
  latestSnapshotTime: string | null;
};

export interface AccountConfigFields {
  riskPolicy: string;
  stopLossPct: number | null;
  takeProfitPct: number | null;
  tradeSizePct: number;
  maxPositionPct: number;
  instrumentMode: string;
  goalMinReturnPct: number | null;
  goalMaxReturnPct: number | null;
  goalPeriod: string | null;
  learningEnabled: boolean;
  optionStrikeOffsetPct: number | null;
  optionMinDte: number | null;
  optionMaxDte: number | null;
  optionType: string | null;
  targetDeltaMin: number | null;
  targetDeltaMax: number | null;
  maxPremiumPerTrade: number | null;
  maxContractsPerTrade: number | null;
  ivRankMin: number | null;
  ivRankMax: number | null;
  rollDteThreshold: number | null;
  optionProfitTakePct: number | null;
  optionMaxLossPct: number | null;
  activeStrategy?: string;
  rotation?: RotationSettings | null;
}

// Book-owned rotation scheduling (ADR 014); nested object on the account payloads.
export interface RotationSettings {
  enabled?: boolean | null;
  schedule?: string[] | null;
  lookbackDays?: number | null;
}

export interface RotationPolicySettings {
  minTradesInWindow: number;
  outperformanceThresholdBps: number;
  cooldownDays: number;
  riskAdjustedReturnWeight: number;
  stabilityWeight: number;
  drawdownPenaltyWeight: number;
}

export interface BookConfiguration extends AccountConfigFields {
  name: string;
  status: string;
  isDefault: boolean;
  strategy: string;
  startEquity: number;
  currentCash: number;
  currentEquity: number;
  tradeUniverses: string[];
  maxTradesPerRun: number | null;
  rotation: RotationSettings;
  rotationPolicy: RotationPolicySettings;
}

export interface AccountMutableIdentityFields {
  strategy: string;
  descriptiveName: string;
}

export interface AccountConfigOptionDefaults {
  goalPeriod: string;
  riskPolicy: string;
  instrumentMode: string;
}

export interface AccountConfigOptions {
  goalPeriods: string[];
  riskPolicies: string[];
  instrumentModes: string[];
  optionTypes: string[];
  defaults: AccountConfigOptionDefaults;
}

export type AccountSummary = AccountListItem & AccountConfigFields & {
  initialCash: number;
  settlementCash: number;
  liveBenchmarkReturnPct: number | null;
  liveAlphaPct: number | null;
  liveBenchmarkEquity: number | null;
  liveBenchmarkStartTime: string | null;
  liveBenchmarkEndTime: string | null;
};

export type LiveBenchmarkOverlay = {
  benchmark: string;
  startTime: string;
  endTime: string;
  startingEquity: number;
  endingEquity: number;
  benchmarkEquity: number;
  accountReturnPct: number;
  benchmarkReturnPct: number;
  alphaPct: number;
  points: Array<{
    time: string;
    accountEquity: number;
    benchmarkEquity: number;
  }>;
};

export type AccountDetail = {
  account: AccountSummary;
  books?: BookConfiguration[];
  latestBacktest: BacktestRunSummary | null;
  latestBacktestMetrics?: LatestBacktestMetrics | null;
  liveBenchmarkOverlay?: LiveBenchmarkOverlay | null;
  snapshots: Array<{
    time: string;
    cash: number;
    marketValue: number;
    equity: number;
    realizedPnl: number;
    unrealizedPnl: number;
  }>;
  trades: Array<{
    ticker: string;
    side: string;
    qty: number;
    price: number;
    fee: number;
    tradeTime: string;
    note: string | null;
  }>;
  positions: Array<{
    ticker: string;
    qty: number;
    avgCost: number;
    marketPrice: number;
    marketValue: number;
    unrealizedPnl: number;
  }>;
};

export type AnalysisPosition = {
  ticker: string;
  qty: number;
  avgCost: number;
  costBasis: number;
  marketPrice: number;
  marketValue: number;
  unrealizedPnl: number;
  unrealizedPnlPct: number;
  portfolioPct: number;
};

export type AccountAnalysis = {
  accountReturnPct: number;
  benchmarkReturnPct: number | null;
  benchmarkTicker: string | null;
  alphaPct: number | null;
  realizedPnl: number;
  unrealizedPnl: number;
  equity: number;
  topWinners: AnalysisPosition[];
  topLosers: AnalysisPosition[];
  improvementNotes: string[];
};

export type AccountParamsUpdate = Partial<AccountConfigFields> & Partial<AccountMutableIdentityFields>;

export type BookParamsUpdate = AccountParamsUpdate & {
  tradeUniverses?: string[];
  maxTradesPerRun?: number;
  rotationPolicy?: Partial<RotationPolicySettings>;
};
