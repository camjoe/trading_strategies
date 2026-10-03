export interface OverviewFacts {
  schema_version: number;
  database_tables: number;
  strategies: { total: number; by_style: Record<string, number> };
  adrs: number;
  python_tests_floor: number;
}

export interface AboutStat {
  label: string;
  value: string;
  detail: string;
  targetTab?: string;
}
