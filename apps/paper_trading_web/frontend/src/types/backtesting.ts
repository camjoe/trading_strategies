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
