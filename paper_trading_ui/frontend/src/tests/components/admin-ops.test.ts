import { describe, expect, it } from "vitest";

import { renderOperationsOverview, renderPromotionOverview } from "../../components/admin-ops";
import type { OperationsOverviewResponse, PromotionOverviewResponse } from "../../types";

describe("renderOperationsOverview", () => {
  it("renders job health cards and artifact panels", () => {
    const payload: OperationsOverviewResponse = {
      jobs: [
        {
          key: "daily_paper_trading",
          label: "Daily Paper Trading",
          cadence: "daily",
          windowLabel: "2026-04-17",
          status: "ok",
          currentRunPresent: true,
          currentRunComplete: true,
          currentLog: { name: "daily_paper_trading_20260417_131001.log", modifiedAt: "2026-04-17T13:10:01Z" },
          lastSuccess: { name: "daily_paper_trading_20260417_131001.log", modifiedAt: "2026-04-17T13:10:01Z" },
          runHint: "python3 -m trading.interfaces.runtime.jobs.daily_paper_trading",
        },
      ],
      dailyBacktestRefreshArtifacts: [
        { name: "daily_backtest_refresh_20260417_131001.json", modifiedAt: "2026-04-17T13:12:00Z", sizeBytes: 2048 },
      ],
      dailySnapshotArtifacts: [],
      databaseBackups: [],
    };

    const html = renderOperationsOverview(payload);
    expect(html).toContain("Daily Paper Trading");
    expect(html).toContain("Healthy");
    expect(html).toContain("daily_backtest_refresh_20260417_131001.json");
    expect(html).toContain("No daily snapshot artifacts found");
  });
});

describe("renderPromotionOverview", () => {
  it("renders the assessment summary and review history", () => {
    const payload: PromotionOverviewResponse = {
      assessment: {
        account_name: "alpha_account",
        strategy_name: "trend",
        evaluation_generated_at: "2026-04-17T13:15:00Z",
        stage: "promotion_review",
        status: "ready_for_review",
        ready_for_live: true,
        live_trading_enabled: false,
        overall_confidence: 0.91,
        data_gaps: [],
        blockers: [],
        warnings: ["Needs operator sign-off."],
        next_action: "Approve or reject promotion review.",
      },
      history: [
        {
          review: {
            id: 7,
            account_name_snapshot: "alpha_account",
            strategy_name: "trend",
            review_state: "requested",
            assessment_stage: "promotion_review",
            assessment_status: "ready_for_review",
            ready_for_live: true,
            overall_confidence: 0.91,
            requested_by: "operator",
            reviewed_by: null,
            operator_summary_note: "Ready for ops review.",
            created_at: "2026-04-17T13:16:00Z",
            updated_at: "2026-04-17T13:17:00Z",
            closed_at: null,
          },
          events: [
            {
              id: 11,
              event_seq: 1,
              event_type: "requested",
              actor_name: "operator",
              from_review_state: null,
              to_review_state: "requested",
              note: "Ready for ops review.",
              created_at: "2026-04-17T13:16:00Z",
            },
          ],
        },
      ],
    };

    const html = renderPromotionOverview(payload);
    expect(html).toContain("ready_for_review");
    expect(html).toContain("0.91");
    expect(html).toContain("Review #7");
    expect(html).toContain("Needs operator sign-off.");
    expect(html).toContain("Ready for ops review.");
  });
});
