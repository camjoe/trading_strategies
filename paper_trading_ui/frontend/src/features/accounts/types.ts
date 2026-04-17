import type { AccountAnalysis, AccountDetail, AccountListItem } from "../../types";

export interface AccountsFeatureOptions {
  onAccountsLoaded?: (accounts: AccountListItem[]) => Promise<void> | void;
  onOpenRunReport?: (runId: number) => Promise<void> | void;
}

export type DetailSection = "summary" | "analysis" | "positions" | "trades" | "snapshots" | "config";

export interface LoadAccountDetailOptions {
  section?: DetailSection;
}

export interface AccountsFeature {
  getAccounts: () => AccountListItem[];
  loadAccounts: () => Promise<void>;
  loadAccountDetail: (accountName: string, options?: LoadAccountDetailOptions) => Promise<void>;
  snapshotAll: () => Promise<void>;
  wireActions: () => void;
}

export interface AccountsState {
  cachedAccounts: AccountListItem[];
  currentDetail: AccountDetail | null;
  currentAccountName: string | null;
  currentTradePage: number;
  currentAnalysis: AccountAnalysis | null;
  currentDetailSection: DetailSection;
  accountBrowserOpen: boolean;
  tradePageSize: number;
}
