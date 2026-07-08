import { esc } from "../../lib/format";
import type { AccountDetail } from "../../types/accounts";
import { instrumentModeOptions, optionTypeOptions, riskPolicyOptions } from "./config-options";

export function renderConfigEditor(detail: AccountDetail, showActions: boolean): string {
  if (!showActions) {
    return `<div class="empty">Config editing is unavailable for this account.</div>`;
  }

  return `<div id="editParamsPanel" class="edit-params-panel" hidden>
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
      </details>

      <div class="edit-params-actions">
        <button id="editParamsSaveBtn" type="button">Save</button>
        <button id="editParamsCancelBtn" type="button">Cancel</button>
        <div id="editParamsMsg"></div>
      </div>
    </div>`;
}
