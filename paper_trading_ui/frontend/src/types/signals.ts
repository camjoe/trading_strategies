export interface ManualTradeRequest {
  ticker: string;
  side: "buy" | "sell";
  qty: number;
  price: number;
  fee: number;
}

export interface FeatureDescription {
  label: string;
  description: string;
  range: string;
}

export interface ProviderStatus {
  name: string;
  source_label: string;
  available: boolean;
  fetched_at: string;
  key_scores: Record<string, number>;
  description?: string;
  data_sources?: string[];
  feature_descriptions?: Record<string, FeatureDescription>;
  signal_logic?: string;
}

export interface ProviderStatusResponse {
  providers: ProviderStatus[];
}

export interface SignalOutput {
  strategy: string;
  signal: "buy" | "hold" | "sell";
  available: boolean;
  features: Record<string, number>;
  reason?: string;
  interpretation?: string;
  signal_logic?: string;
  feature_descriptions?: Record<string, FeatureDescription>;
}

export interface SignalsResponse {
  ticker: string;
  signals: SignalOutput[];
}
