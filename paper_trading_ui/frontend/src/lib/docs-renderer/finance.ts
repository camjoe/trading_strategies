import financeData from "../../assets/finance.json";
import { esc } from "./shared";
import type { FinanceTerm } from "./types";

const FINANCE_UI_SECTION_MAP: Record<string, string> = {
  "Execution and Risk Controls": "Execution & Risk Controls",
  "Performance and Risk": "Performance & Benchmarking",
  "Options and Volatility": "Options / Derivatives",
  "Backtesting and Validation": "Data & Backtesting Integrity",
  "Technical Analysis": "Technical Signals",
  "Trading Strategies": "Trading Strategies",
  "Asset Classes": "Asset Classes",
  "Areas of Focus": "Asset Classes",
};

const FINANCE_SECTION_ORDER = [
  "Performance & Benchmarking",
  "Execution & Risk Controls",
  "Options / Derivatives",
  "Data & Backtesting Integrity",
  "Technical Signals",
  "Trading Strategies",
  "Asset Classes",
];

const FINANCE_SECTION_HEADERS: Record<string, [string, string]> = {
  "Technical Signals": ["Concept", "Description"],
  "Trading Strategies": ["Strategy", "Description"],
  "Asset Classes": ["Asset Class", "Notes"],
};

const UI_TERM_LABELS: Record<string, string> = {
  DTE: "DTE (Days to Expiration)",
};

const TRADING_STRATEGIES_EVAL_LIST = `      <p class="ref-subsection-label">Evaluation Framework</p>
      <ul class="ref-eval-list">
        <li>Universe and timeframe</li>
        <li>Signal definition</li>
        <li>Entry / exit rules</li>
        <li>Position sizing</li>
        <li>Transaction cost and slippage assumptions</li>
        <li>Risk limits</li>
        <li>Validation method (walk-forward, out-of-sample)</li>
        <li>Metrics: Sharpe ratio, max drawdown, turnover, hit rate</li>
      </ul>`;

function buildFinanceSection(title: string, terms: FinanceTerm[]): string {
  const [col1, col2] = FINANCE_SECTION_HEADERS[title] ?? ["Term", "Definition"];
  const rows = terms
    .map((term) => {
      const label = esc(UI_TERM_LABELS[term.term] ?? term.term);
      const def = esc(term.definition);
      return `          <tr><td>${label}</td><td>${def}</td></tr>`;
    })
    .join("\n");

  const extra = title === "Trading Strategies" ? `\n${TRADING_STRATEGIES_EVAL_LIST}` : "";

  return `    <div class="ref-section">
      <h3>${esc(title)}</h3>
      <table class="ref-table ref-table--software">
        <thead><tr><th>${esc(col1)}</th><th>${esc(col2)}</th></tr></thead>
        <tbody>
${rows}
        </tbody>
      </table>${extra}
    </div>`;
}

export function buildFinanceCard(): string {
  const terms = (financeData.terms as FinanceTerm[]).filter(
    (term) => term.use === "both" || term.use === "ui",
  );

  const bySection: Record<string, FinanceTerm[]> = {};
  for (const term of terms) {
    const section = FINANCE_UI_SECTION_MAP[term.group];
    if (!section) continue;
    (bySection[section] ??= []).push(term);
  }

  const sections = FINANCE_SECTION_ORDER.filter((section) => bySection[section]?.length)
    .map((section) => buildFinanceSection(section, bySection[section]))
    .join("\n\n");

  return `  <section class="card ref-card">
    <div class="ref-card-head">
      <h2>Financial &amp; Market Knowledge</h2>
      <button type="button" class="ref-card-toggle-all" data-ref-card-toggle-all aria-label="Expand all" data-tooltip="Expand all">⊞</button>
    </div>

${sections}
  </section>`;
}
