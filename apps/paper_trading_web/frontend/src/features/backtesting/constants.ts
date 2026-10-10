import { esc } from "../../lib/format";

export const PREFLIGHT_INPUT_SELECTOR =
  'input[name="tickersFile"], input[name="universeHistoryDir"], input[name="start"], input[name="end"], input[name="lookbackMonths"], input[name="allowApproximateLeaps"], select[name="account"]';

export const BACKTEST_ACCOUNT_SELECT_SELECTOR = "#backtestAccountSelect";

export const BACKTEST_WARNINGS_SELECTOR = "#runBacktestWarnings";

export const BACKTEST_RUNS_LIST_SELECTOR = "#backtestRunsList";
export const BACKTEST_REPORT_VIEW_SELECTOR = "#backtestReportView";
export const REFRESH_BACKTESTS_BUTTON_SELECTOR = "#refreshBacktestsBtn";
export const RUN_BACKTEST_FORM_SELECTOR = "#runBacktestForm";

export const BACKTEST_RUN_ITEM_SELECTOR = ".bt-run-item";
export const QUICK_LOOKBACK_BUTTONS_SELECTOR = ".bt-quick-buttons";

export function renderDownMessage(message: string): string {
  return `<div class="down">${esc(message)}</div>`;
}
