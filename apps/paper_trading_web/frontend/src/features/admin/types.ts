import type { AccountSummary } from "../../types/accounts";


export interface DeleteResponse {
  status: string;
  deleted: {
    accounts: number;
    trades: number;
    orders: number;
    orderFills: number;
    equitySnapshots: number;
    backtestRuns: number;
    backtestTrades: number;
    backtestEquitySnapshots: number;
    walkForwardGroups: number;
    walkForwardGroupRuns: number;
    promotionReviews: number;
    promotionReviewEvents: number;
    riskSnapshots: number;
    riskDecisions: number;
  };
}


export interface CreateResponse {
  status: string;
  account: AccountSummary;
}


export interface CsvExportFile {
  name: string;
  sizeBytes: number;
}


export interface CsvExportBatch {
  name: string;
  modifiedAt: string;
  files: CsvExportFile[];
}


export interface CsvExportListResponse {
  exports: CsvExportBatch[];
}


export interface CsvPreviewResponse {
  exportName: string;
  fileName: string;
  header: string[];
  rows: string[][];
  returned: number;
  truncated: boolean;
}


export interface AdminFeatureOptions {
  onAccountsChanged?: () => Promise<void> | void;
}


export interface AdminFeature {
  wireActions: () => void;
  loadDeleteAccounts: () => Promise<void>;
}


export type AdminSection = "jobs" | "accounts" | "promotions" | "artifacts";
