import type { AccountListItem } from "../../types";

export interface BacktestingFeature {
  setAccounts: (accounts: AccountListItem[]) => void;
  loadBacktestRuns: () => Promise<void>;
  loadBacktestReport: (runId: number) => Promise<void>;
  wireActions: () => void;
}
