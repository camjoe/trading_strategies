import { esc } from "../../lib/format";
import type { AccountDetail } from "../../types/accounts";

function formatOptionalNumber(value: number | null | undefined, digits = 2): string {
  return value == null ? "—" : value.toFixed(digits);
}

function formatOptionalList(values: string[] | null | undefined): string {
  return values && values.length ? esc(values.join(", ")) : "—";
}

function configStat(label: string, value: string): string {
  return `
    <div class="analysis-stat">
      <span class="label">${esc(label)}</span>
      <span>${value}</span>
    </div>
  `;
}

export function renderConfigSummary(detail: AccountDetail): string {
  const account = detail.account;
  return `
    <div class="config-summary-stack">
      <section class="config-summary-card">
        <h5>Core Settings</h5>
        <div class="analysis-summary">
          ${configStat("Display Name", esc(account.displayName))}
          ${configStat("Strategy", esc(account.strategy))}
          ${configStat("Instrument Mode", esc(account.instrumentMode))}
          ${configStat("Risk Policy", esc(account.riskPolicy))}
          ${configStat("Learning", account.learningEnabled ? "On" : "Off")}
          ${configStat("Trade Size %", formatOptionalNumber(account.tradeSizePct * 100, 1))}
          ${configStat("Max Position %", formatOptionalNumber(account.maxPositionPct * 100, 1))}
        </div>
      </section>
      <section class="config-summary-card">
        <h5>Goals & Risk Guardrails</h5>
        <div class="analysis-summary">
          ${configStat("Goal Min Return %", formatOptionalNumber(account.goalMinReturnPct, 1))}
          ${configStat("Goal Max Return %", formatOptionalNumber(account.goalMaxReturnPct, 1))}
          ${configStat("Goal Period", esc(account.goalPeriod ?? "—"))}
          ${configStat("Stop Loss %", formatOptionalNumber(account.stopLossPct, 2))}
          ${configStat("Take Profit %", formatOptionalNumber(account.takeProfitPct, 2))}
          ${configStat("Profit Take %", formatOptionalNumber(account.profitTakePct, 2))}
          ${configStat("Max Loss %", formatOptionalNumber(account.maxLossPct, 2))}
        </div>
      </section>
      <section class="config-summary-card">
        <h5>Options Settings</h5>
        <div class="analysis-summary">
          ${configStat("Option Type", esc(account.optionType ?? "—"))}
          ${configStat("Strike Offset %", formatOptionalNumber(account.optionStrikeOffsetPct, 2))}
          ${configStat("Min DTE", formatOptionalNumber(account.optionMinDte, 0))}
          ${configStat("Max DTE", formatOptionalNumber(account.optionMaxDte, 0))}
          ${configStat("Target Delta Min", formatOptionalNumber(account.targetDeltaMin, 2))}
          ${configStat("Target Delta Max", formatOptionalNumber(account.targetDeltaMax, 2))}
          ${configStat("IV Rank Min", formatOptionalNumber(account.ivRankMin, 1))}
          ${configStat("IV Rank Max", formatOptionalNumber(account.ivRankMax, 1))}
          ${configStat("Max Premium / Trade", formatOptionalNumber(account.maxPremiumPerTrade, 2))}
          ${configStat("Max Contracts / Trade", formatOptionalNumber(account.maxContractsPerTrade, 0))}
        </div>
      </section>
      <section class="config-summary-card">
        <h5>Rotation Settings</h5>
        <div class="analysis-summary">
          ${configStat("Rotation Enabled", account.rotationEnabled ? "On" : "Off")}
          ${configStat("Rotation Mode", esc(account.rotationMode ?? "—"))}
          ${configStat("Optimality Mode", esc(account.rotationOptimalityMode ?? "—"))}
          ${configStat("Interval Days", formatOptionalNumber(account.rotationIntervalDays, 0))}
          ${configStat("Interval Minutes", formatOptionalNumber(account.rotationIntervalMinutes, 0))}
          ${configStat("Lookback Days", formatOptionalNumber(account.rotationLookbackDays, 0))}
          ${configStat("Active Strategy", esc(account.rotationActiveStrategy ?? "—"))}
          ${configStat("Overlay Mode", esc(account.rotationOverlayMode ?? "—"))}
          ${configStat("Overlay Min Tickers", formatOptionalNumber(account.rotationOverlayMinTickers, 0))}
          ${configStat("Overlay Confidence", formatOptionalNumber(account.rotationOverlayConfidenceThreshold, 2))}
        </div>
        <div class="config-summary-note">
          <strong>Schedule:</strong> ${formatOptionalList(account.rotationSchedule)}
        </div>
        <div class="config-summary-note">
          <strong>Overlay Watchlist:</strong> ${formatOptionalList(account.rotationOverlayWatchlist)}
        </div>
      </section>
    </div>
  `;
}
