import { describe, expect, it } from "vitest";

import {
  renderBacktestReport,
  renderBacktestRunCard,
  renderBacktestRunResult,
  renderWalkForwardResult,
  warningListHtml,
} from "../../components/backtesting";
import type { BacktestReport, BacktestRunResult, BacktestRunSummary, WalkForwardResult } from "../../types";

describe("warningListHtml", () => {
  it("renders an empty-state message when no warnings exist", () => {
    const html = warningListHtml([]);
    expect(html).toContain("No financial-model warnings");
  });

  it("escapes warning text to avoid HTML injection", () => {
    const html = warningListHtml(["<script>alert('xss')</script>"]);
    expect(html).toContain("&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;");
    expect(html).not.toContain("<script>");
  });
});

describe("renderBacktestRunResult", () => {
  const base: BacktestRunResult = {
    runId: 42,
    accountName: "trend_v1",
    startDate: "2026-01-01",
    endDate: "2026-03-31",
    tradeCount: 10,
    endingEquity: 10500.0,
    totalReturnPct: 5.0,
    benchmarkReturnPct: 3.0,
    alphaPct: 2.0,
    maxDrawdownPct: -1.5,
    sharpeRatio: 1.3,
    sortinoRatio: 1.9,
    calmarRatio: 0.8,
    winRatePct: 60.0,
    profitFactor: 1.7,
    avgTradeReturnPct: 2.4,
    warnings: [],
  };

  it("renders run id, account name, and date range", () => {
    const html = renderBacktestRunResult(base);
    expect(html).toContain("Run 42");
    expect(html).toContain("trend_v1");
    expect(html).toContain("2026-01-01");
    expect(html).toContain("2026-03-31");
  });

  it("renders trade count and equity", () => {
    const html = renderBacktestRunResult(base);
    expect(html).toContain("Trades: 10");
    expect(html).toContain("10,500");
  });

  it("renders benchmark and alpha when available", () => {
    const html = renderBacktestRunResult(base);
    expect(html).toContain("Benchmark");
    expect(html).toContain("Alpha");
  });

  it("shows unavailable when benchmark is null", () => {
    const html = renderBacktestRunResult({ ...base, benchmarkReturnPct: null, alphaPct: null });
    expect(html).toContain("unavailable");
  });

  it("renders the empty-state warnings message when warnings array is empty", () => {
    const html = renderBacktestRunResult(base);
    expect(html).toContain("No financial-model warnings");
  });

  it("renders warning items when present", () => {
    const html = renderBacktestRunResult({ ...base, warnings: ["daily bars only"] });
    expect(html).toContain("daily bars only");
  });

  it("renders richer trade and risk metrics", () => {
    const html = renderBacktestRunResult(base);
    expect(html).toContain("Sharpe");
    expect(html).toContain("Sortino");
    expect(html).toContain("Win Rate");
    expect(html).toContain("Profit Factor");
  });
});

describe("renderWalkForwardResult", () => {
  const base: WalkForwardResult = {
    accountName: "trend_v1",
    startDate: "2026-01-01",
    endDate: "2026-03-31",
    windowCount: 3,
    runIds: [101, 102, 103],
    averageReturnPct: 1.2,
    medianReturnPct: 1.0,
    bestReturnPct: 2.3,
    worstReturnPct: 0.1,
  };

  it("renders account name, date range, and window count", () => {
    const html = renderWalkForwardResult(base);
    expect(html).toContain("trend_v1");
    expect(html).toContain("2026-01-01");
    expect(html).toContain("2026-03-31");
    expect(html).toContain("Windows: 3");
  });

  it("renders run IDs joined by comma", () => {
    const html = renderWalkForwardResult(base);
    expect(html).toContain("101, 102, 103");
  });

  it("shows 'none' when there are no run IDs", () => {
    const html = renderWalkForwardResult({ ...base, runIds: [] });
    expect(html).toContain("Run IDs: none");
  });
});

describe("renderBacktestRunCard", () => {
  const base: BacktestRunSummary = {
    runId: 7,
    runName: "smoke-run",
    accountName: "trend_v1",
    strategy: "trend",
    startDate: "2026-01-01",
    endDate: "2026-01-31",
    createdAt: "2026-02-01T00:00:00Z",
    slippageBps: 5.0,
    feePerTrade: 0.0,
    tickersFile: "trading/config/trade_universe.txt",
  };

  it("renders run id and run name", () => {
    const html = renderBacktestRunCard(base);
    expect(html).toContain("#7");
    expect(html).toContain("smoke-run");
  });

  it("renders '(unnamed)' when runName is null", () => {
    const html = renderBacktestRunCard({ ...base, runName: null });
    expect(html).toContain("(unnamed)");
  });

  it("renders account name as a chip", () => {
    const html = renderBacktestRunCard(base);
    expect(html).toContain('class="chip"');
    expect(html).toContain("trend_v1");
  });

  it("includes the data-run-id attribute", () => {
    const html = renderBacktestRunCard(base);
    expect(html).toContain('data-run-id="7"');
  });
});

describe("renderBacktestReport", () => {
  const base: BacktestReport = {
    run_id: 99,
    run_name: "final-run",
    account_name: "trend_v1",
    strategy: "trend",
    benchmark_ticker: "SPY",
    start_date: "2026-01-01",
    end_date: "2026-01-31",
    created_at: "2026-02-01T00:00:00Z",
    slippage_bps: 5.0,
    fee_per_trade: 0.25,
    tickers_file: "trading/config/trade_universe.txt",
    notes: null,
    warnings: ["daily bars only", "approximate pricing"],
    trade_count: 4,
    starting_equity: 10000.0,
    ending_equity: 10200.0,
    total_return_pct: 2.0,
    max_drawdown_pct: -0.5,
    benchmark_return_pct: 1.2,
    alpha_pct: 0.8,
    sharpe_ratio: 1.4,
    sortino_ratio: 2.1,
    calmar_ratio: 0.9,
    win_rate_pct: 57.0,
    profit_factor: 1.6,
    avg_trade_return_pct: 1.9,
    snapshots: [
      {
        snapshot_time: "2026-01-01",
        cash: 10000.0,
        market_value: 0.0,
        equity: 10000.0,
        realized_pnl: 0.0,
        unrealized_pnl: 0.0,
      },
      {
        snapshot_time: "2026-01-31",
        cash: 2000.0,
        market_value: 8200.0,
        equity: 10200.0,
        realized_pnl: 100.0,
        unrealized_pnl: 100.0,
      },
    ],
  };

  it("renders run id, run name, and account", () => {
    const html = renderBacktestReport(base);
    expect(html).toContain("Run 99");
    expect(html).toContain("final-run");
    expect(html).toContain("trend_v1");
  });

  it("renders equity and return values", () => {
    const html = renderBacktestReport(base);
    expect(html).toContain("10,000");
    expect(html).toContain("10,200");
  });

  it("renders trade count and slippage", () => {
    const html = renderBacktestReport(base);
    expect(html).toContain("Trades: 4");
    expect(html).toContain("5.00 bps");
  });

  it("renders analytics grid and equity curve", () => {
    const html = renderBacktestReport(base);
    expect(html).toContain("Sharpe");
    expect(html).toContain("Win Rate");
    expect(html).toContain("Equity Curve");
    expect(html).toContain("<svg");
  });

  it("renders pipe-separated warnings as individual items", () => {
    const html = renderBacktestReport(base);
    expect(html).toContain("daily bars only");
    expect(html).toContain("approximate pricing");
  });

  it("shows empty-state when warnings array is empty", () => {
    const html = renderBacktestReport({ ...base, warnings: [] });
    expect(html).toContain("No financial-model warnings");
  });

  it("renders '(unnamed)' when run_name is null", () => {
    const html = renderBacktestReport({ ...base, run_name: null });
    expect(html).toContain("(unnamed)");
  });
});
