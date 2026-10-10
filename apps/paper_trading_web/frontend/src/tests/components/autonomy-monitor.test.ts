/* eslint-disable @typescript-eslint/no-explicit-any */
import { describe, expect, it } from "vitest";

import type {
  AutonomyDailyWorkflow,
  GovernanceCheckStatus,
  BurnInStatus,
  RotationDecision,
  RiskSummary,
} from "../../types/autonomy-monitor";

// Import the actual render functions from the panels module
import {
  renderAccountOverview,
  renderBooksPanel,
  renderDailyWorkflowPanel,
  renderGovernancePanel,
  renderBurnInPanel,
  renderRotationsPanel,
  renderRiskSummaryPanel,
} from "../../components/autonomy-monitor-panels";

describe("Autonomy Monitor render functions", () => {
  describe("renderAccountOverview", () => {
    it("renders account overview with positive return", () => {
      const account = {
        account_id: 1,
        name: "Test Account",
        total_equity: 50000,
        total_cash: 10000,
        positions_market_value: 40000,
        initial_cash: 45000,
        return_pct: 0.11,
        book_count: 3,
      };

      const html = renderAccountOverview(account as any);
      expect(html).toContain("Account Overview");
      expect(html).toContain("$50,000.00");
      expect(html).toContain("+0.11%");
    });

    it("renders account overview with negative return", () => {
      const account = {
        account_id: 2,
        name: "Loss Account",
        total_equity: 44000,
        total_cash: 15000,
        positions_market_value: 29000,
        initial_cash: 45000,
        return_pct: -0.022,
        book_count: 2,
      };

      const html = renderAccountOverview(account as any);
      expect(html).toContain("down");
      expect(html).toContain("-0.02%");
    });

    it("handles zero values", () => {
      const account = {
        account_id: 3,
        name: "Zero Account",
        total_equity: 0,
        total_cash: 0,
        positions_market_value: 0,
        initial_cash: 0,
        return_pct: 0,
        book_count: 0,
      };

      const html = renderAccountOverview(account as any);
      expect(html).toContain("$0.00");
    });

    it("handles large numbers", () => {
      const account = {
        account_id: 4,
        name: "Large Account",
        total_equity: 999999999.99,
        total_cash: 500000000,
        positions_market_value: 499999999.99,
        initial_cash: 1000000,
        return_pct: 99.99,
        book_count: 1000,
      };

      const html = renderAccountOverview(account as any);
      expect(html).toContain("999,999,999.99");
    });
  });

  describe("renderBooksPanel", () => {
    it("renders empty state when no books", () => {
      const html = renderBooksPanel([]);
      expect(html).toContain("No books configured");
    });

    it("renders books table with active book", () => {
      const books = [
        {
          book_id: 1,
          name: "Momentum",
          strategy: "Trend Following",
          current_equity: 20000,
          current_cash: 5000,
          return_pct: 0.15,
          status: "active",
          start_equity: 20000,
          positions_market_value: 15000,
          latest_metrics: { return_pct: 0.15, drawdown_pct: -0.05, hit_rate: 0.65, trade_count: 10, metric_date: "2026-05-10" },
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-05-10T00:00:00Z",
        },
      ] as any;

      const html = renderBooksPanel(books);
      expect(html).toContain("Momentum");
      expect(html).toContain("status-active");
      // hit_rate is stored as a 0–1 fraction, so it has to be scaled to render as a percentage.
      expect(html).toContain("Hit Rate: 65.0%");
    });

    it("renders paused book", () => {
      const books = [
        {
          book_id: 2,
          name: "MeanRev",
          strategy: "StatArb",
          current_equity: 18000,
          current_cash: 3000,
          return_pct: -0.08,
          status: "paused",
          start_equity: 20000,
          positions_market_value: 15000,
          latest_metrics: { return_pct: -0.08, drawdown_pct: -0.12, hit_rate: null, trade_count: 5, metric_date: "2026-05-09" },
          created_at: "2026-02-01T00:00:00Z",
          updated_at: "2026-05-10T00:00:00Z",
        },
      ] as any;

      const html = renderBooksPanel(books);
      expect(html).toContain("status-paused");
      // A null hit_rate is genuinely absent.
      expect(html).toContain("—");
    });

    it("renders closed book", () => {
      const books = [
        {
          book_id: 3,
          name: "Old",
          strategy: "OldStrat",
          current_equity: 100,
          current_cash: 50,
          return_pct: 0,
          status: "closed",
          start_equity: 100,
          positions_market_value: 50,
          latest_metrics: { return_pct: 0, drawdown_pct: 0, hit_rate: 0, trade_count: 0, metric_date: null },
          created_at: "2025-01-01T00:00:00Z",
          updated_at: "2025-12-01T00:00:00Z",
        },
      ] as any;

      const html = renderBooksPanel(books);
      expect(html).toContain("status-closed");
      // A 0 hit rate is a measured result, not missing data.
      expect(html).toContain("Hit Rate: 0.0%");
    });
  });

  describe("renderDailyWorkflowPanel", () => {
    it("renders no workflow data state when null", () => {
      const html = renderDailyWorkflowPanel(null);
      expect(html).toContain("No workflow data available");
    });

    it("renders workflow with success status", () => {
      const workflow: AutonomyDailyWorkflow = {
        latest_run_date: "2026-05-10",
        latest_run_time: "2026-05-10T14:30:00Z",
        status: "success",
        completed_steps: 5,
        duration_seconds: 42.5,
        failed_step: null,
        step_results: [
          { step: "collect_data", name: "Collect", status: "ok", started_at: "2026-05-10T14:30:00Z", finished_at: "2026-05-10T14:31:00Z", duration_seconds: 60, details: {}, error: null },
          { step: "analyze", name: "Analyze", status: "ok", started_at: "2026-05-10T14:31:00Z", finished_at: "2026-05-10T14:32:00Z", duration_seconds: 60, details: {}, error: null },
          { step: "trade", name: "Trade", status: "ok", started_at: "2026-05-10T14:32:00Z", finished_at: "2026-05-10T14:33:00Z", duration_seconds: 60, details: {}, error: null },
          { step: "report", name: "Report", status: "ok", started_at: "2026-05-10T14:33:00Z", finished_at: "2026-05-10T14:34:00Z", duration_seconds: 60, details: {}, error: null },
          { step: "archive", name: "Archive", status: "ok", started_at: "2026-05-10T14:34:00Z", finished_at: "2026-05-10T14:35:00Z", duration_seconds: 60, details: {}, error: null },
        ],
      };

      const html = renderDailyWorkflowPanel(workflow);
      expect(html).toContain("status-success");
      expect(html).toContain("5 / 5 steps completed");
    });

    it("renders workflow with failed status", () => {
      const workflow: AutonomyDailyWorkflow = {
        latest_run_date: "2026-05-10",
        latest_run_time: "2026-05-10T14:30:00Z",
        status: "failed",
        completed_steps: 2,
        duration_seconds: 15.0,
        failed_step: "analyze_market_data",
        step_results: [
          { step: "collect_data", name: "Collect", status: "ok", started_at: "2026-05-10T14:30:00Z", finished_at: "2026-05-10T14:31:00Z", duration_seconds: 60, details: {}, error: null },
          { step: "analyze", name: "Analyze", status: "failed", started_at: "2026-05-10T14:31:00Z", finished_at: "2026-05-10T14:32:00Z", duration_seconds: 60, details: {}, error: "Market closed" },
        ],
      };

      const html = renderDailyWorkflowPanel(workflow);
      expect(html).toContain("status-failed");
      expect(html).toContain("analyze_market_data");
    });
  });

  describe("renderGovernancePanel", () => {
    it("renders all governance jobs", () => {
      const governance: Record<string, GovernanceCheckStatus> = {
        w1_leaderboard: { status: "success", last_run: "2026-05-09T00:00:00Z", has_results: true },
        w2_promotion: { status: "failed", last_run: "2026-05-02T00:00:00Z", has_results: false },
        w3_allocation: { status: "not_run", last_run: null, has_results: false },
        m1_risk_rebaseline: { status: "success", last_run: "2026-04-30T00:00:00Z", has_results: true },
        m2_parameter_governance: { status: "not_run", last_run: null, has_results: false },
        m3_performance_audit: { status: "success", last_run: "2026-04-01T00:00:00Z", has_results: true },
      };

      const html = renderGovernancePanel(governance);
      expect(html).toContain("Governance Checks");
      expect(html).toContain("W1 Leaderboard");
      expect(html).toContain("status-success");
    });

    it("renders missing jobs as not_run", () => {
      const governance: Record<string, GovernanceCheckStatus> = {};
      const html = renderGovernancePanel(governance);
      expect(html).toContain("status-not_run");
    });

    it("renders structured governance results with cross-navigation controls", () => {
      const html = renderGovernancePanel({
        w1_leaderboard: {
          status: "success",
          last_run: "2026-05-09T00:00:00Z",
          has_results: true,
          result: {
            week: "2026-W19",
            accounts: [{
              account_name: "alpha",
              books: [{
                book_name: "growth",
                strategy_name: "trend",
                rank: 1,
                avg_return_pct: 2.5,
              }],
            }],
          },
        },
      });
      expect(html).toContain("View results");
      expect(html).toContain('data-governance-result="w1_leaderboard"');
      expect(html).toContain('data-account="alpha"');
      expect(html).toContain('data-book="growth"');
      expect(html).toContain('data-strategy="trend"');
      expect(html).toContain("Avg Return Pct");
    });
  });

  describe("renderBurnInPanel", () => {
    it("renders burn-in not ready", () => {
      const burnIn: BurnInStatus = {
        consecutive_successes: 3,
        min_required_successes: 10,
        failure_count: 2,
        ready_for_live: false,
        status_as_of: "2026-05-10T12:00:00Z",
        window_days: 30,
      };

      const html = renderBurnInPanel(burnIn);
      expect(html).toContain("3/10");
      expect(html).toContain("Not Ready");
    });

    it("renders burn-in ready for live", () => {
      const burnIn: BurnInStatus = {
        consecutive_successes: 10,
        min_required_successes: 10,
        failure_count: 0,
        ready_for_live: true,
        status_as_of: "2026-05-10T12:00:00Z",
        window_days: 30,
      };

      const html = renderBurnInPanel(burnIn);
      expect(html).toContain("Ready for Live");
      expect(html).toContain("width: 100%");
    });

    it("handles missing status_as_of", () => {
      const burnIn: BurnInStatus = {
        consecutive_successes: 5,
        min_required_successes: 10,
        failure_count: 0,
        ready_for_live: false,
        status_as_of: null,
        window_days: 30,
      };

      const html = renderBurnInPanel(burnIn);
      expect(html).not.toContain("As of");
    });
  });

  describe("renderRotationsPanel", () => {
    it("renders empty state", () => {
      const html = renderRotationsPanel([]);
      expect(html).toContain("No recent rotations");
    });

    it("renders rotations table", () => {
      const rotations: RotationDecision[] = [
        {
          rotation_id: 1,
          book_id: 1,
          book_name: "Momentum",
          incumbent: "Trend1",
          challenger: "Trend2",
          reason: "Performance",
          decision_time: "2026-05-10T10:00:00Z",
        },
      ];

      const html = renderRotationsPanel(rotations);
      expect(html).toContain("Momentum");
      expect(html).toContain("→");
    });
  });

  describe("renderRiskSummaryPanel", () => {
    it("renders kill switch normal", () => {
      const riskSummary: RiskSummary = {
        kill_switch_triggered: false,
        recent_violations: [],
        violation_count: 0,
      };

      const html = renderRiskSummaryPanel(riskSummary);
      expect(html).toContain("🟢 Normal");
      expect(html).toContain("No recent violations");
    });

    it("renders kill switch triggered", () => {
      const riskSummary: RiskSummary = {
        kill_switch_triggered: true,
        recent_violations: [
          {
            decision_time: "2026-05-10T14:30:00Z",
            book_id: 1,
            book_name: "Test",
            reason: "Max loss",
            action: "block",
          },
        ] as any,
        violation_count: 1,
      };

      const html = renderRiskSummaryPanel(riskSummary);
      expect(html).toContain("🔴 TRIGGERED");
      expect(html).toContain("Recent Violations (1)");
    });
  });
});
