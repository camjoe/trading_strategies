export interface AccountExposureRow {
  accountId: number;
  accountName: string;
  snapshotTime: string | null;
  cash: number | null;
  marketValue: number | null;
  equity: number | null;
  positionCount: number;
}

export interface PortfolioExposure {
  accounts: AccountExposureRow[];
  accountCount: number;
  accountsWithSnapshots: number;
  totalCash: number;
  totalMarketValue: number;
  totalEquity: number;
}

export interface SymbolConcentrationRow {
  symbol: string;
  sector: string;
  marketValue: number;
  portfolioPct: number;
  accountCount: number;
  accountNames: string[];
}

export interface SectorConcentrationRow {
  sector: string;
  marketValue: number;
  portfolioPct: number;
  symbolCount: number;
}

export interface PortfolioConcentration {
  symbols: SymbolConcentrationRow[];
  sectors: SectorConcentrationRow[];
  totalMarketValue: number;
}

export interface PortfolioRollupResponse {
  exposure: PortfolioExposure;
  concentration: PortfolioConcentration;
}
