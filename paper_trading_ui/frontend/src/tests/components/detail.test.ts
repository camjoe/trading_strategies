import { describe, expect, it } from "vitest";

import type { AccountDetail } from "../../types";
import { renderDetail } from "../../components/detail";

describe("renderDetail", () => {
  it("renders latest backtest section when available", () => {
    const detail: AccountDetail = {
      account: {
        name: "acct1",
        displayName: "Acct One",
        strategy: "Momentum",
        instrumentMode: "equity",
        riskPolicy: "none",
        benchmark: "SPY",
        initialCash: 1000,
        equity: 1100,
        totalChange: 100,
        totalChangePct: 10,
        changeSinceLastSnapshot: 5,
        latestSnapshotTime: "2026-03-15T00:00:00Z",
      },
      latestBacktest: {
        runId: 12,
        runName: "run-a",
        accountName: "acct1",
        strategy: "Momentum",
        startDate: "2026-01-01",
        endDate: "2026-02-01",
        createdAt: "2026-03-15T00:00:00Z",
        slippageBps: 5,
        feePerTrade: 1,
        tickersFile: "trading/config/trade_universe.txt",
      },
      snapshots: [
        {
          time: "2026-03-15T00:00:00Z",
          cash: 700,
          marketValue: 400,
          equity: 1100,
          realizedPnl: 10,
          unrealizedPnl: 90,
        },
      ],
      trades: [
        {
          ticker: "AAPL",
          side: "buy",
          qty: 1,
          price: 100,
          fee: 0,
          tradeTime: "2026-03-14T00:00:00Z",
        },
      ],
    };

    const html = renderDetail(detail);
    expect(html).toContain("Latest Backtest Run 12");
    expect(html).toContain("Open Report");
    expect(html).toContain("Snapshot This Account");
    expect(html).toContain("AAPL");
  });

  it("renders empty states when latest backtest/snapshots/trades are absent", () => {
    const detail: AccountDetail = {
      account: {
        name: "acct2",
        displayName: "Acct Two",
        strategy: "Trend",
        instrumentMode: "equity",
        riskPolicy: "none",
        benchmark: "QQQ",
        initialCash: 1000,
        equity: 900,
        totalChange: -100,
        totalChangePct: -10,
        changeSinceLastSnapshot: null,
        latestSnapshotTime: null,
      },
      latestBacktest: null,
      snapshots: [],
      trades: [],
    };

    const html = renderDetail(detail);
    expect(html).toContain("No backtest run found for this account yet");
    expect(html).toContain("No snapshots yet");
    expect(html).toContain("No trades yet");
  });
});
