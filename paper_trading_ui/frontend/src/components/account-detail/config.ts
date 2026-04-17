import { esc } from "../../lib/format";
import { getAccountConfigOptions, renderOptionTags } from "../../lib/account-config-options";
import type { AccountDetail } from "../../types";

type DetailSectionName = "summary" | "analysis" | "positions" | "trades" | "snapshots" | "config";

function riskPolicyOptions(currentPolicy: string): string {
  return renderOptionTags(getAccountConfigOptions()?.riskPolicies ?? [], currentPolicy);
}

function instrumentModeOptions(currentMode: string): string {
  return renderOptionTags(getAccountConfigOptions()?.instrumentModes ?? [], currentMode);
}

function rotationModeOptions(currentMode: string): string {
  return renderOptionTags(getAccountConfigOptions()?.rotationModes ?? [], currentMode);
}

function rotationOptimalityOptions(currentMode: string): string {
  return renderOptionTags(getAccountConfigOptions()?.rotationOptimalityModes ?? [], currentMode);
}

function rotationOverlayModeOptions(currentMode: string): string {
  return renderOptionTags(getAccountConfigOptions()?.rotationOverlayModes ?? [], currentMode);
}

function optionTypeOptions(currentType: string | null): string {
  return renderOptionTags(getAccountConfigOptions()?.optionTypes ?? [], currentType ?? undefined, {
    includeEmpty: true,
  });
}

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

function renderConfigSummary(detail: AccountDetail): string {
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

export function renderConfigSection(
  detail: AccountDetail,
  options: { activeSection: DetailSectionName; showActions: boolean },
): string {
  const { activeSection, showActions } = options;
  return `
    <article class="detail-section-panel" data-detail-panel="config" ${activeSection === "config" ? "" : "hidden"}>
      <div class="config-section-head">
        <div>
          <h4>Account Configuration</h4>
          <p class="muted">Review the current account setup, then open the editor when you want to update parameters.</p>
        </div>
        ${showActions ? `<button id="editParamsBtn" type="button">Edit Parameters</button>` : ""}
      </div>
      ${renderConfigSummary(detail)}
      ${showActions ? `<div id="editParamsPanel" class="edit-params-panel" hidden>
      <div class="edit-params-section">
        <h5>Core</h5>
        <div class="bt-row">
          <div class="bt-field">
            <span>Display Name</span>
            <input id="editDisplayNameInput" type="text" value="${esc(detail.account.displayName)}" />
          </div>
          <div class="bt-field">
            <span>Strategy</span>
            <input id="editStrategyInput" type="text" value="${esc(detail.account.strategy)}" />
          </div>
          <div class="bt-field">
            <span>Instrument Mode</span>
            <select id="editInstrumentModeSelect">
              ${instrumentModeOptions(detail.account.instrumentMode)}
            </select>
          </div>
          <div class="bt-field">
            <span>Risk Policy</span>
            <select id="editRiskPolicySelect">
              ${riskPolicyOptions(detail.account.riskPolicy)}
            </select>
          </div>
        </div>
        <div class="bt-row">
          <div class="bt-field">
            <span>Stop Loss %</span>
            <input id="editStopLossPctInput" type="number" step="0.01" value="${detail.account.stopLossPct ?? ""}" placeholder="e.g. 5.0" />
          </div>
          <div class="bt-field">
            <span>Take Profit %</span>
            <input id="editTakeProfitPctInput" type="number" step="0.01" value="${detail.account.takeProfitPct ?? ""}" placeholder="e.g. 15.0" />
          </div>
          <div class="bt-field">
            <span>Learning</span>
            <select id="editLearningEnabledSelect">
              <option value="false"${!detail.account.learningEnabled ? " selected" : ""}>Off</option>
              <option value="true"${detail.account.learningEnabled ? " selected" : ""}>On</option>
            </select>
          </div>
        </div>
      </div>

      <details class="edit-params-section">
        <summary>Return Goals</summary>
        <div class="bt-row">
          <div class="bt-field">
            <span>Min Return %</span>
            <input id="editGoalMinReturnInput" type="number" step="0.1" value="${detail.account.goalMinReturnPct ?? ""}" placeholder="e.g. 2.0" />
          </div>
          <div class="bt-field">
            <span>Max Return %</span>
            <input id="editGoalMaxReturnInput" type="number" step="0.1" value="${detail.account.goalMaxReturnPct ?? ""}" placeholder="e.g. 10.0" />
          </div>
          <div class="bt-field">
            <span>Period</span>
            <input id="editGoalPeriodInput" type="text" value="${esc(detail.account.goalPeriod ?? "")}" placeholder="monthly" />
          </div>
        </div>
      </details>

      <details class="edit-params-section">
        <summary>Options Settings</summary>
        <div class="bt-row">
          <div class="bt-field">
            <span>Option Type</span>
            <select id="editOptionTypeSelect">
              ${optionTypeOptions(detail.account.optionType)}
            </select>
          </div>
          <div class="bt-field">
            <span>Strike Offset %</span>
            <input id="editOptionStrikeOffsetInput" type="number" step="0.01" value="${detail.account.optionStrikeOffsetPct ?? ""}" />
          </div>
          <div class="bt-field">
            <span>Min DTE</span>
            <input id="editOptionMinDteInput" type="number" step="1" value="${detail.account.optionMinDte ?? ""}" />
          </div>
          <div class="bt-field">
            <span>Max DTE</span>
            <input id="editOptionMaxDteInput" type="number" step="1" value="${detail.account.optionMaxDte ?? ""}" />
          </div>
        </div>
        <div class="bt-row">
          <div class="bt-field">
            <span>Target Delta Min</span>
            <input id="editTargetDeltaMinInput" type="number" step="0.01" min="0" max="1" value="${detail.account.targetDeltaMin ?? ""}" />
          </div>
          <div class="bt-field">
            <span>Target Delta Max</span>
            <input id="editTargetDeltaMaxInput" type="number" step="0.01" min="0" max="1" value="${detail.account.targetDeltaMax ?? ""}" />
          </div>
          <div class="bt-field">
            <span>IV Rank Min</span>
            <input id="editIvRankMinInput" type="number" step="1" min="0" max="100" value="${detail.account.ivRankMin ?? ""}" />
          </div>
          <div class="bt-field">
            <span>IV Rank Max</span>
            <input id="editIvRankMaxInput" type="number" step="1" min="0" max="100" value="${detail.account.ivRankMax ?? ""}" />
          </div>
        </div>
        <div class="bt-row">
          <div class="bt-field">
            <span>Max Premium / Trade</span>
            <input id="editMaxPremiumInput" type="number" step="1" value="${detail.account.maxPremiumPerTrade ?? ""}" />
          </div>
          <div class="bt-field">
            <span>Max Contracts / Trade</span>
            <input id="editMaxContractsInput" type="number" step="1" value="${detail.account.maxContractsPerTrade ?? ""}" />
          </div>
          <div class="bt-field">
            <span>Roll DTE Threshold</span>
            <input id="editRollDteThresholdInput" type="number" step="1" value="${detail.account.rollDteThreshold ?? ""}" />
          </div>
        </div>
        <div class="bt-row">
          <div class="bt-field">
            <span>Profit Take %</span>
            <input id="editProfitTakePctInput" type="number" step="0.1" value="${detail.account.profitTakePct ?? ""}" />
          </div>
          <div class="bt-field">
            <span>Max Loss %</span>
            <input id="editMaxLossPctInput" type="number" step="0.1" value="${detail.account.maxLossPct ?? ""}" />
          </div>
        </div>
      </details>

      <details class="edit-params-section">
        <summary>Rotation Settings</summary>
        <div class="bt-row">
          <div class="bt-field">
            <span>Rotation Enabled</span>
            <select id="editRotationEnabledSelect">
              <option value="false"${!detail.account.rotationEnabled ? " selected" : ""}>Off</option>
              <option value="true"${detail.account.rotationEnabled ? " selected" : ""}>On</option>
            </select>
          </div>
          <div class="bt-field">
            <span>Rotation Mode</span>
            <select id="editRotationModeSelect">
              ${rotationModeOptions(detail.account.rotationMode ?? "time")}
            </select>
          </div>
          <div class="bt-field">
            <span>Optimality Mode</span>
            <select id="editRotationOptimalityModeSelect">
              ${rotationOptimalityOptions(detail.account.rotationOptimalityMode ?? "previous_period_best")}
            </select>
          </div>
        </div>
        <div class="bt-row">
          <div class="bt-field">
            <span>Interval Days</span>
            <input id="editRotationIntervalDaysInput" type="number" step="1" min="1" value="${detail.account.rotationIntervalDays ?? ""}" />
          </div>
          <div class="bt-field">
            <span>Interval Minutes</span>
            <input id="editRotationIntervalMinutesInput" type="number" step="1" min="1" value="${detail.account.rotationIntervalMinutes ?? ""}" />
          </div>
          <div class="bt-field">
            <span>Lookback Days</span>
            <input id="editRotationLookbackDaysInput" type="number" step="1" min="1" value="${detail.account.rotationLookbackDays ?? ""}" />
          </div>
          <div class="bt-field">
            <span>Active Index</span>
            <input id="editRotationActiveIndexInput" type="number" step="1" min="0" value="${detail.account.rotationActiveIndex ?? 0}" />
          </div>
        </div>
        <div class="bt-row">
          <div class="bt-field">
            <span>Active Strategy</span>
            <input id="editRotationActiveStrategyInput" type="text" value="${esc(detail.account.rotationActiveStrategy ?? "")}" placeholder="trend" />
          </div>
          <div class="bt-field">
            <span>Last Rotated At</span>
            <input id="editRotationLastAtInput" type="text" value="${esc(detail.account.rotationLastAt ?? "")}" placeholder="2026-03-18T12:00:00Z" />
          </div>
        </div>
        <div class="bt-row">
          <div class="bt-field" style="flex:1">
            <span>Rotation Schedule (comma-separated)</span>
            <input id="editRotationScheduleInput" type="text" value="${esc((detail.account.rotationSchedule ?? []).join(","))}" placeholder="trend,mean_reversion,breakout" />
          </div>
        </div>
        <div class="bt-row">
          <div class="bt-field">
            <span>Regime Risk-On Strategy</span>
            <input id="editRotationRegimeRiskOnInput" type="text" value="${esc(detail.account.rotationRegimeStrategyRiskOn ?? "")}" placeholder="trend" />
          </div>
          <div class="bt-field">
            <span>Regime Neutral Strategy</span>
            <input id="editRotationRegimeNeutralInput" type="text" value="${esc(detail.account.rotationRegimeStrategyNeutral ?? "")}" placeholder="ma_crossover" />
          </div>
          <div class="bt-field">
            <span>Regime Risk-Off Strategy</span>
            <input id="editRotationRegimeRiskOffInput" type="text" value="${esc(detail.account.rotationRegimeStrategyRiskOff ?? "")}" placeholder="mean_reversion" />
          </div>
        </div>
        <div class="bt-row">
          <div class="bt-field">
            <span>Overlay Mode</span>
            <select id="editRotationOverlayModeSelect">
              ${rotationOverlayModeOptions(detail.account.rotationOverlayMode ?? "none")}
            </select>
          </div>
          <div class="bt-field">
            <span>Overlay Min Tickers</span>
            <input id="editRotationOverlayMinTickersInput" type="number" step="1" min="1" value="${detail.account.rotationOverlayMinTickers ?? ""}" />
          </div>
          <div class="bt-field">
            <span>Overlay Confidence Threshold</span>
            <input id="editRotationOverlayConfidenceThresholdInput" type="number" step="0.01" min="0.01" max="1" value="${detail.account.rotationOverlayConfidenceThreshold ?? ""}" placeholder="0.50" />
          </div>
        </div>
        <div class="bt-row">
          <div class="bt-field" style="flex:1">
            <span>Overlay Watchlist (comma-separated)</span>
            <input id="editRotationOverlayWatchlistInput" type="text" value="${esc((detail.account.rotationOverlayWatchlist ?? []).join(","))}" placeholder="AAPL,MSFT,NVDA" />
          </div>
        </div>
      </details>

      <div class="edit-params-actions">
        <button id="editParamsSaveBtn" type="button">Save</button>
        <button id="editParamsCancelBtn" type="button">Cancel</button>
        <div id="editParamsMsg"></div>
      </div>
    </div>` : `<div class="empty">Config editing is unavailable for this account.</div>`}
    </article>
  `;
}
