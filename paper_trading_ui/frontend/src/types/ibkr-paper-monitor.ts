/**
 * Type definitions for IBKR Paper Account Monitor API responses.
 */

export interface IbkrPaperAccountOverview {
  account: {
    account_id: number;
    name: string;
    initial_cash: number;
    total_equity: number;
    total_cash: number;
    positions_market_value: number;
    return_pct: number;
    sleeve_count: number;
  };
  sleeves: IbkrPaperSleeve[];
  daily_workflow: IbkrDailyWorkflow | null;
  governance_checks: Record<string, GovernanceCheckStatus>;
  burn_in_status: BurnInStatus;
  recent_rotations: RotationDecision[];
  risk_summary: RiskSummary;
}

export interface IbkrPaperSleeve {
  sleeve_id: number;
  name: string;
  status: "active" | "paused" | "retired";
  strategy: string;
  start_equity: number;
  current_equity: number;
  current_cash: number;
  positions_market_value: number;
  return_pct: number;
  latest_metrics: {
    return_pct: number | null;
    drawdown_pct: number | null;
    hit_rate: number | null;
    trade_count: number | null;
    metric_date: string | null;
  };
  created_at: string;
  updated_at: string;
}

export interface IbkrDailyWorkflow {
  latest_run_date: string;
  latest_run_time: string;
  status: "success" | "failed" | "running" | "pending";
  completed_steps: number;
  failed_step: string | null;
  duration_seconds: number;
  step_results: DagStepResult[];
}

export interface DagStepResult {
  step: string;
  name: string;
  status: "ok" | "failed" | "skipped" | "running";
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  details: Record<string, any>;
  error: string | null;
}

export interface GovernanceCheckStatus {
  last_run: string | null;
  status: "success" | "failed" | "not_run" | "unknown";
  has_results: boolean;
}

export interface BurnInStatus {
  ready_for_live: boolean;
  consecutive_successes: number;
  min_required_successes: number;
  failure_count: number;
  window_days: number;
  status_as_of: string | null;
}

export interface RotationDecision {
  rotation_id: number;
  sleeve_id: number;
  sleeve_name: string;
  decision_time: string;
  incumbent: string;
  challenger: string;
  reason: string;
}

export interface RiskSummary {
  kill_switch_triggered: boolean;
  recent_violations: RiskViolation[];
  violation_count: number;
}

export interface RiskViolation {
  decision_time: string;
  sleeve_id: number;
  sleeve_name: string;
  reason: string;
  action: "block" | "rescale" | "allow";
}

export interface IbkrPaperAccountListItem {
  account_id: number;
  name: string;
  initial_cash: number;
  total_equity: number;
  total_cash: number;
  positions_market_value: number;
  return_pct: number;
  sleeve_count: number;
}
