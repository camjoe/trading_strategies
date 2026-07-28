import type { AccountConfigFields } from "./accounts";

export interface AdminCreateAccountPayload extends Partial<AccountConfigFields> {
  name: string | undefined;
  strategy: string | undefined;
  initialCash: number | undefined;
  benchmarkTicker?: string;
  descriptiveName: string | undefined;
}

export interface OperationLogRef {
  name: string;
  modifiedAt: string;
}

export interface OperationJobStatus {
  key: string;
  label: string;
  cadence: string;
  windowLabel: string;
  status: "ok" | "warning" | "missing";
  currentRunPresent: boolean;
  currentRunComplete: boolean;
  currentLog: OperationLogRef | null;
  lastSuccess: OperationLogRef | null;
  runHint: string;
}

export interface OperationArtifact {
  name: string;
  modifiedAt: string;
  sizeBytes: number;
}

export interface OperationsOverviewResponse {
  jobs: OperationJobStatus[];
  dailySnapshotArtifacts: OperationArtifact[];
  databaseBackups: OperationArtifact[];
}

export interface PromotionAssessment {
  account_name: string | null;
  strategy_name: string | null;
  evaluation_generated_at: string | null;
  stage: string;
  status: string;
  ready_for_live: boolean;
  live_trading_enabled: boolean;
  overall_confidence: number;
  data_gaps: string[];
  blockers: string[];
  warnings: string[];
  next_action: string | null;
}

export interface PromotionEvaluationSummary {
  blendedScore: number | null;
  overallConfidence: number;
  backtestConfidence: number;
  paperLiveConfidence: number;
  dataGaps: string[];
  backtestStale: boolean;
}

// Advisory backtest staleness; never affects scores or decisions.
export interface BacktestFreshness {
  available: boolean;
  ageDays: number | null;
  isStale: boolean;
  staleThresholdDays: number | null;
}

export interface PromotionEvaluationDetail {
  backtest: {
    available: boolean;
    returnPct: number | null;
    tradeCount: number | null;
    snapshotCount: number | null;
    maxDrawdownPct: number | null;
  };
  walkForward: {
    available: boolean;
    windowCount: number;
    averageReturnPct: number | null;
    bestReturnPct: number | null;
    worstReturnPct: number | null;
  };
  paperLive: {
    available: boolean;
    returnPct: number | null;
    snapshotCount: number | null;
    sourceLevel: string | null;
    strategyIsolated: boolean;
  };
  confidence: PromotionEvaluationSummary;
  dataGaps: string[];
  backtestFreshness: BacktestFreshness;
}

export interface PromotionReviewRecord {
  id: number | null;
  account_name_snapshot: string | null;
  strategy_name: string | null;
  review_state: string;
  assessment_stage: string;
  assessment_status: string;
  ready_for_live: boolean;
  overall_confidence: number;
  requested_by: string | null;
  reviewed_by: string | null;
  operator_summary_note: string | null;
  created_at: string | null;
  updated_at: string | null;
  closed_at: string | null;
}

export interface PromotionReviewEvent {
  id: number | null;
  event_seq: number;
  event_type: string;
  actor_name: string | null;
  from_review_state: string | null;
  to_review_state: string | null;
  note: string | null;
  created_at: string | null;
}

export interface PromotionReviewHistoryEntry {
  review: PromotionReviewRecord;
  events: PromotionReviewEvent[];
}

export interface PromotionOverviewResponse {
  assessment: PromotionAssessment;
  evaluation: PromotionEvaluationDetail;
  history: PromotionReviewHistoryEntry[];
}
