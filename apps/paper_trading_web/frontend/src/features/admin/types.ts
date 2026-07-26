import type { AccountSummary } from "../../types/accounts";


export interface DeleteResponse {
  status: string;
  deleted: {
    accountName: string;
  };
}


export interface DeletePreviewResponse {
  status: string;
  preview: {
    accountName: string;
    descriptiveName: string;
    strategy: string;
  };
}


export interface CreateResponse {
  status: string;
  account: AccountSummary;
}


export interface AdminFeatureOptions {
  onAccountsChanged?: () => Promise<void> | void;
}


export interface AdminFeature {
  wireActions: () => void;
  loadDeleteAccounts: () => Promise<void>;
}


export type AdminSection = "jobs" | "accounts" | "promotions" | "parameters" | "artifacts";

export interface ParameterEntry {
  name: string;
  value: string;
  source: string;
}

export interface ParameterGroup {
  scope: string;
  note: string | null;
  entries: ParameterEntry[];
}

export interface ParameterSourceResponse {
  groups: ParameterGroup[];
}
