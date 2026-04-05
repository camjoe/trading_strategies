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
  riskPolicy?: string;
}

export interface ManualTradeRequest {
  ticker: string;
  side: "buy" | "sell";
  qty: number;
  price: number;
  fee: number;
}
