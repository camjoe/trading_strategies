export type AccountSummary = {
  name: string;
  displayName: string;
  strategy: string;
  instrumentMode: string;
  riskPolicy: string;
  benchmark: string;
  initialCash: number;
  equity: number;
  totalChange: number;
  totalChangePct: number;
  changeSinceLastSnapshot: number | null;
  latestSnapshotTime: string | null;
  // config fields
  stopLossPct: number | null;
  takeProfitPct: number | null;
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
};

export type AccountDetail = {
  account: AccountSummary;
  latestBacktest: BacktestRunSummary | null;
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
  }>;
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
  warnings: string;
  trade_count: number;
  starting_equity: number;
  ending_equity: number;
  total_return_pct: number;
  max_drawdown_pct: number;
};

export type LatestBacktestMetrics = {
  runId: number;
  endDate: string;
  totalReturnPct: number;
  maxDrawdownPct: number;
  alphaPct: number | null;
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
  latestBacktest: LatestBacktestMetrics | null;
};

export interface AccountParamsUpdate {
  strategy?: string;
  descriptiveName?: string;
  riskPolicy?: string;
  stopLossPct?: number | null;
  takeProfitPct?: number | null;
  instrumentMode?: string;
  goalMinReturnPct?: number | null;
  goalMaxReturnPct?: number | null;
  goalPeriod?: string;
  learningEnabled?: boolean;
  optionStrikeOffsetPct?: number | null;
  optionMinDte?: number | null;
  optionMaxDte?: number | null;
  optionType?: string | null;
  targetDeltaMin?: number | null;
  targetDeltaMax?: number | null;
  maxPremiumPerTrade?: number | null;
  maxContractsPerTrade?: number | null;
  ivRankMin?: number | null;
  ivRankMax?: number | null;
  rollDteThreshold?: number | null;
  profitTakePct?: number | null;
  maxLossPct?: number | null;
}

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
