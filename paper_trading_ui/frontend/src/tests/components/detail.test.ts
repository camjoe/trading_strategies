import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { AccountDetail } from "../../types";
import { renderDetail } from "../../components/detail";
import { resetAccountConfigOptions, setAccountConfigOptions } from "../../lib/account-config-options";

describe("renderDetail", () => {
  beforeEach(() => {
    setAccountConfigOptions({
      goalPeriods: ["monthly", "weekly", "quarterly", "yearly"],
      riskPolicies: ["none", "fixed_stop", "take_profit", "stop_and_target"],
      instrumentModes: ["equity", "leaps"],
      optionTypes: ["call", "put", "both"],
      rotationModes: ["time", "optimal", "regime"],
      rotationOptimalityModes: ["previous_period_best", "average_return", "hybrid_weighted"],
      rotationOverlayModes: ["none", "news", "social", "news_social"],
      defaults: {
        goalPeriod: "monthly",
        riskPolicy: "none",
        instrumentMode: "equity",
        rotationMode: "time",
        rotationOptimalityMode: "previous_period_best",
        rotationOverlayMode: "none",
      },
    });
  });

  afterEach(() => {
    resetAccountConfigOptions();
  });

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
        settlementCash: 0,
        totalChange: 100,
        totalChangePct: 10,
        liveBenchmarkReturnPct: 8,
        liveAlphaPct: 2,
        liveBenchmarkEquity: 1080,
        liveBenchmarkStartTime: "2026-03-14T00:00:00Z",
        liveBenchmarkEndTime: "2026-03-15T00:00:00Z",
        changeSinceLastSnapshot: 5,
        latestSnapshotTime: "2026-03-15T00:00:00Z",
        tradeSizePct: 0.1,
        maxPositionPct: 0.2,
        stopLossPct: null,
        takeProfitPct: null,
        goalMinReturnPct: null,
        goalMaxReturnPct: null,
        goalPeriod: null,
        learningEnabled: false,
        optionStrikeOffsetPct: null,
        optionMinDte: null,
        optionMaxDte: null,
        optionType: null,
        targetDeltaMin: null,
        targetDeltaMax: null,
        maxPremiumPerTrade: null,
        maxContractsPerTrade: null,
        ivRankMin: null,
        ivRankMax: null,
        rollDteThreshold: null,
        profitTakePct: null,
        maxLossPct: null,
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
      latestBacktestMetrics: {
        runId: 12,
        endDate: "2026-02-01",
        totalReturnPct: 14,
        maxDrawdownPct: -4,
        sharpeRatio: 1.5,
        winRatePct: 58,
        profitFactor: 1.8,
      },
      liveBenchmarkOverlay: {
        benchmark: "SPY",
        startTime: "2026-03-14T00:00:00Z",
        endTime: "2026-03-15T00:00:00Z",
        startingEquity: 1000,
        endingEquity: 1100,
        benchmarkEquity: 1080,
        accountReturnPct: 10,
        benchmarkReturnPct: 8,
        alphaPct: 2,
        points: [
          { time: "2026-03-14T00:00:00Z", accountEquity: 1040, benchmarkEquity: 1030 },
          { time: "2026-03-15T00:00:00Z", accountEquity: 1100, benchmarkEquity: 1080 },
        ],
      },
      snapshots: [
        {
          time: "2026-03-14T00:00:00Z",
          cash: 650,
          marketValue: 390,
          equity: 1040,
          realizedPnl: 5,
          unrealizedPnl: 35,
        },
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
          note: "manual-import;source=test_investments",
        },
      ],
      positions: [],
    };

    const html = renderDetail(detail);
    expect(html).toContain("Latest Backtest Run 12");
    expect(html).toContain("Open Report");
    expect(html).toContain("Backtest Return");
    expect(html).toContain("Benchmark Return");
    expect(html).toContain("Live Alpha");
    expect(html).toContain("Live vs SPY");
    expect(html).toContain("Live Equity Curve");
    expect(html).toContain("<svg");
    expect(html).toContain("Snapshot This Account");
    expect(html).toContain("Edit Parameters");
    expect(html).toContain('class="detail-section-tab active"');
    expect(html).toContain('data-detail-panel="summary"');
    expect(html).toContain('data-detail-panel="trades" hidden');
    expect(html).toContain("Rotation Settings");
    expect(html).toContain("editRotationModeSelect");
    expect(html).toContain("editRotationScheduleInput");
    expect(html).toContain("editRotationRegimeRiskOnInput");
    expect(html).toContain("editRotationRegimeNeutralInput");
    expect(html).toContain("editRotationRegimeRiskOffInput");
    expect(html).toContain("editParamsPanel");
    expect(html).toContain("AAPL");
    // Add Trade should be hidden by default (not test_account)
    expect(html).not.toContain("addTradeBtn");
    expect(html).not.toContain("addTradePanel");
  });

  it("shows Add Trade panel when showAddTrade is true", () => {
    const detail: AccountDetail = {
      account: {
        name: "test_account",
        displayName: "TEST Account",
        strategy: "Manual",
        instrumentMode: "equity",
        riskPolicy: "none",
        benchmark: "SPY",
        initialCash: 10000,
        equity: 10000,
        settlementCash: 10000,
        totalChange: 0,
        totalChangePct: 0,
        liveBenchmarkReturnPct: null,
        liveAlphaPct: null,
        liveBenchmarkEquity: null,
        liveBenchmarkStartTime: null,
        liveBenchmarkEndTime: null,
        changeSinceLastSnapshot: null,
        latestSnapshotTime: null,
        tradeSizePct: 0.1,
        maxPositionPct: 0.2,
        stopLossPct: null,
        takeProfitPct: null,
        goalMinReturnPct: null,
        goalMaxReturnPct: null,
        goalPeriod: null,
        learningEnabled: false,
        optionStrikeOffsetPct: null,
        optionMinDte: null,
        optionMaxDte: null,
        optionType: null,
        targetDeltaMin: null,
        targetDeltaMax: null,
        maxPremiumPerTrade: null,
        maxContractsPerTrade: null,
        ivRankMin: null,
        ivRankMax: null,
        rollDteThreshold: null,
        profitTakePct: null,
        maxLossPct: null,
      },
      latestBacktest: null,
      latestBacktestMetrics: null,
      liveBenchmarkOverlay: null,
      snapshots: [],
      trades: [],
      positions: [],
    };

    const html = renderDetail(detail, { showAddTrade: true });
    expect(html).toContain("addTradeBtn");
    expect(html).toContain("addTradePanel");
    expect(html).toContain("Submit Trade");
  });

  it("hides Add Trade panel when showAddTrade is false (default)", () => {
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
        settlementCash: 0,
        totalChange: -100,
        totalChangePct: -10,
        liveBenchmarkReturnPct: null,
        liveAlphaPct: null,
        liveBenchmarkEquity: null,
        liveBenchmarkStartTime: null,
        liveBenchmarkEndTime: null,
        changeSinceLastSnapshot: null,
        latestSnapshotTime: null,
        tradeSizePct: 0.1,
        maxPositionPct: 0.2,
        stopLossPct: null,
        takeProfitPct: null,
        goalMinReturnPct: null,
        goalMaxReturnPct: null,
        goalPeriod: null,
        learningEnabled: false,
        optionStrikeOffsetPct: null,
        optionMinDte: null,
        optionMaxDte: null,
        optionType: null,
        targetDeltaMin: null,
        targetDeltaMax: null,
        maxPremiumPerTrade: null,
        maxContractsPerTrade: null,
        ivRankMin: null,
        ivRankMax: null,
        rollDteThreshold: null,
        profitTakePct: null,
        maxLossPct: null,
      },
      latestBacktest: null,
      latestBacktestMetrics: null,
      liveBenchmarkOverlay: null,
      snapshots: [],
      trades: [],
      positions: [],
    };

    const htmlDefault = renderDetail(detail);
    expect(htmlDefault).not.toContain("addTradeBtn");

    const htmlExplicit = renderDetail(detail, { showAddTrade: false });
    expect(htmlExplicit).not.toContain("addTradeBtn");
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
        settlementCash: 0,
        totalChange: -100,
        totalChangePct: -10,
        liveBenchmarkReturnPct: null,
        liveAlphaPct: null,
        liveBenchmarkEquity: null,
        liveBenchmarkStartTime: null,
        liveBenchmarkEndTime: null,
        changeSinceLastSnapshot: null,
        latestSnapshotTime: null,
        tradeSizePct: 0.1,
        maxPositionPct: 0.2,
        stopLossPct: null,
        takeProfitPct: null,
        goalMinReturnPct: null,
        goalMaxReturnPct: null,
        goalPeriod: null,
        learningEnabled: false,
        optionStrikeOffsetPct: null,
        optionMinDte: null,
        optionMaxDte: null,
        optionType: null,
        targetDeltaMin: null,
        targetDeltaMax: null,
        maxPremiumPerTrade: null,
        maxContractsPerTrade: null,
        ivRankMin: null,
        ivRankMax: null,
        rollDteThreshold: null,
        profitTakePct: null,
        maxLossPct: null,
      },
      latestBacktest: null,
      latestBacktestMetrics: null,
      liveBenchmarkOverlay: null,
      snapshots: [],
      trades: [],
      positions: [],
    };

    const html = renderDetail(detail);
    expect(html).toContain("No backtest run found for this account yet");
    expect(html).toContain("No snapshots yet");
    expect(html).toContain("No trades yet");
    expect(html).toContain("Edit Parameters");
    // risk-policy select should render all four options, current one selected
    expect(html).toContain(`value="none" selected`);
    expect(html).toContain(`value="fixed_stop"`);
    expect(html).toContain(`value="take_profit"`);
    expect(html).toContain(`value="stop_and_target"`);
  });
});
