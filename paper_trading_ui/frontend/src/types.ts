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
  profitTakePct: number | null;
  maxLossPct: number | null;
  rotationEnabled?: boolean;
  rotationMode?: string;
  rotationOptimalityMode?: string;
  rotationIntervalDays?: number | null;
  rotationIntervalMinutes?: number | null;
  rotationLookbackDays?: number | null;
  rotationSchedule?: string[] | null;
  rotationRegimeStrategyRiskOn?: string | null;
  rotationRegimeStrategyNeutral?: string | null;
  rotationRegimeStrategyRiskOff?: string | null;
  rotationOverlayMode?: string;
  rotationOverlayMinTickers?: number | null;
  rotationOverlayConfidenceThreshold?: number | null;
  rotationOverlayWatchlist?: string[] | null;
  rotationActiveIndex?: number | null;
  rotationLastAt?: string | null;
  rotationActiveStrategy?: string | null;
}

export interface AccountMutableIdentityFields {
  strategy: string;
  descriptiveName: string;
}

export interface AdminCreateAccountPayload extends Partial<AccountConfigFields> {
  name: string | undefined;
  strategy: string | undefined;
  initialCash: number | undefined;
  benchmarkTicker: string;
  descriptiveName: string | undefined;
}

export interface AccountConfigOptionDefaults {
  goalPeriod: string;
  riskPolicy: string;
  instrumentMode: string;
  rotationMode: string;
  rotationOptimalityMode: string;
  rotationOverlayMode: string;
}

export interface AccountConfigOptions {
  goalPeriods: string[];
  riskPolicies: string[];
  instrumentModes: string[];
  optionTypes: string[];
  rotationModes: string[];
  rotationOptimalityModes: string[];
  rotationOverlayModes: string[];
  defaults: AccountConfigOptionDefaults;
}

export type AccountSummary = AccountListItem & AccountConfigFields & {
  initialCash: number;
  settlementCash: number;
  liveBenchmarkReturnPct?: number | null;
  liveAlphaPct?: number | null;
  liveBenchmarkEquity?: number | null;
  liveBenchmarkStartTime?: string | null;
  liveBenchmarkEndTime?: string | null;
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

export type BacktestRunSummary = {
  runId: number;
  runName: string | null;
  accountName: string;
  strategy: string;
  startDate: string;
  endDate: string;
  createdAt: string;
  slippageBps: number;
  feePerTrade: number;
  tickersFile: string;
};

export type BacktestRunResult = {
  runId: number;
  accountName: string;
  startDate: string;
  endDate: string;
  tradeCount: number;
  endingEquity: number;
  totalReturnPct: number;
  benchmarkReturnPct: number | null;
  alphaPct: number | null;
  maxDrawdownPct: number;
  sharpeRatio?: number | null;
  sortinoRatio?: number | null;
  calmarRatio?: number | null;
  winRatePct?: number | null;
  profitFactor?: number | null;
  avgTradeReturnPct?: number | null;
  warnings: string[];
};

export type WalkForwardResult = {
  accountName: string;
  startDate: string;
  endDate: string;
  windowCount: number;
  runIds: number[];
  averageReturnPct: number;
  medianReturnPct: number;
  bestReturnPct: number;
  worstReturnPct: number;
};

export type BacktestReport = {
  run_id: number;
  run_name: string | null;
  account_name: string;
  strategy: string;
  benchmark_ticker: string;
  start_date: string;
  end_date: string;
  created_at: string;
  slippage_bps: number;
  fee_per_trade: number;
  tickers_file: string;
  notes: string | null;
  warnings: string[];
  trade_count: number;
  starting_equity: number;
  ending_equity: number;
  total_return_pct: number;
  max_drawdown_pct: number;
  benchmark_return_pct?: number | null;
  alpha_pct?: number | null;
  sharpe_ratio?: number | null;
  sortino_ratio?: number | null;
  calmar_ratio?: number | null;
  win_rate_pct?: number | null;
  profit_factor?: number | null;
  avg_trade_return_pct?: number | null;
  snapshots?: Array<{
    snapshot_time: string;
    cash: number;
    market_value: number;
    equity: number;
    realized_pnl: number;
    unrealized_pnl: number;
  }>;
  trades?: Array<{
    trade_time: string;
    ticker: string;
    side: string;
    qty: number;
    price: number;
    fee: number;
  }>;
};

export type LatestBacktestMetrics = {
  runId: number;
  endDate: string;
  totalReturnPct: number;
  maxDrawdownPct: number;
  sharpeRatio?: number | null;
  sortinoRatio?: number | null;
  calmarRatio?: number | null;
  winRatePct?: number | null;
  profitFactor?: number | null;
  avgTradeReturnPct?: number | null;
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
};

export type AccountParamsUpdate = Partial<AccountConfigFields> & Partial<AccountMutableIdentityFields>;

export interface ManualTradeRequest {
  ticker: string;
  side: "buy" | "sell";
  qty: number;
  price: number;
  fee: number;
}

export interface FeatureDescription {
  label: string;
  description: string;
  range: string;
}

export interface ProviderStatus {
  name: string;
  source_label: string;
  available: boolean;
  fetched_at: string;
  key_scores: Record<string, number>;
  // new fields from backend
  description?: string;
  data_sources?: string[];
  feature_descriptions?: Record<string, FeatureDescription>;
  signal_logic?: string;
}

export interface ProviderStatusResponse {
  providers: ProviderStatus[];
}

export interface SignalOutput {
  strategy: string;
  signal: "buy" | "hold" | "sell";
  available: boolean;
  features: Record<string, number>;
  reason?: string;
  interpretation?: string;
  signal_logic?: string;
  feature_descriptions?: Record<string, FeatureDescription>;
}

export interface SignalsResponse {
  ticker: string;
  signals: SignalOutput[];
}
