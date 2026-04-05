import { currency, esc } from "../lib/format";
import type { AccountDetail } from "../types";

export interface DetailRenderOptions {
  tradePage?: number;
  tradePageSize?: number;
}

const RISK_POLICY_OPTIONS = ["none", "fixed_stop", "take_profit", "stop_and_target"] as const;

function riskPolicyOptions(currentPolicy: string): string {
  return RISK_POLICY_OPTIONS.map(
    (opt) => `<option value="${opt}"${currentPolicy === opt ? " selected" : ""}>${opt}</option>`,
  ).join("");
}

const INSTRUMENT_MODE_OPTIONS = ["equity", "leaps"] as const;

function instrumentModeOptions(currentMode: string): string {
  return INSTRUMENT_MODE_OPTIONS.map(
    (opt) => `<option value="${opt}"${currentMode === opt ? " selected" : ""}>${opt}</option>`,
  ).join("");
}

export function renderDetail(detail: AccountDetail, options: DetailRenderOptions = {}): string {
  const tradePageSize = Math.max(1, options.tradePageSize ?? 20);
  const totalTrades = detail.trades.length;
  const totalTradePages = Math.max(1, Math.ceil(totalTrades / tradePageSize));
  const tradePage = Math.min(Math.max(1, options.tradePage ?? 1), totalTradePages);
  const viewedStart = totalTrades === 0 ? 0 : (tradePage - 1) * tradePageSize + 1;
  const viewedEnd = totalTrades === 0 ? 0 : Math.min(tradePage * tradePageSize, totalTrades);

  const snapRows = detail.snapshots
    .slice(0, 25)
    .map(
      (s) => `
      <tr>
        <td>${new Date(s.time).toLocaleString()}</td>
        <td>${currency.format(s.equity)}</td>
        <td>${currency.format(s.cash)}</td>
        <td>${currency.format(s.marketValue)}</td>
      </tr>
    `,
    )
    .join("");

  const tradeStart = Math.max(0, totalTrades - tradePage * tradePageSize);
  const tradeEnd = totalTrades - (tradePage - 1) * tradePageSize;
  let previousDayKey = "";
  let dayBand = 0;

  const tradeRows = detail.trades
    .slice(tradeStart, tradeEnd)
    .reverse()
    .map((t) => {
      const tradeDate = new Date(t.tradeTime);
      const dayKey = `${tradeDate.getFullYear()}-${tradeDate.getMonth() + 1}-${tradeDate.getDate()}`;
      if (dayKey !== previousDayKey) {
        dayBand += 1;
        previousDayKey = dayKey;
      }
      const dayClass = dayBand % 2 === 0 ? " trade-row--alt-day" : "";

      return `
      <tr class="trade-row${dayClass}">
        <td>${tradeDate.toLocaleString()}</td>
        <td>${esc(t.ticker)}</td>
        <td class="${t.side === "buy" ? "up" : "down"}">${esc(t.side)}</td>
        <td>${t.qty.toFixed(4)}</td>
        <td>${currency.format(t.price)}</td>
        <td>${currency.format(t.fee)}</td>
      </tr>
    `;
    })
    .join("");

  const latestBacktest = detail.latestBacktest
    ? `
      <div class="bt-result">
        <div><strong>Latest Backtest Run ${detail.latestBacktest.runId}</strong> ${esc(detail.latestBacktest.runName ?? "(unnamed)")}</div>
        <div>Range: ${esc(detail.latestBacktest.startDate)}..${esc(detail.latestBacktest.endDate)} | Created: ${new Date(detail.latestBacktest.createdAt).toLocaleString()}</div>
        <div>Slippage: ${detail.latestBacktest.slippageBps.toFixed(2)} bps | Fee: ${currency.format(detail.latestBacktest.feePerTrade)}</div>
        <button id="openLatestBacktestReportBtn" data-run-id="${detail.latestBacktest.runId}" type="button">Open Report</button>
      </div>
    `
    : `<div class="empty">No backtest run found for this account yet.</div>`;

  return `
    <div class="detail-head">
      <div>
        <h3>${esc(detail.account.displayName)}</h3>
        <p>${esc(detail.account.name)} | ${esc(detail.account.strategy)} | ${esc(detail.account.benchmark)}</p>
      </div>
      <div class="detail-head-actions">
        <button id="editParamsBtn" type="button">Edit Parameters</button>
        <button id="snapshotOneBtn" data-account="${esc(detail.account.name)}">Snapshot This Account</button>
      </div>
    </div>

    <div id="editParamsPanel" class="edit-params-panel" hidden>
      <!-- Core parameters - always visible -->
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

      <!-- Goal parameters -->
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

      <!-- Options parameters -->
      <details class="edit-params-section">
        <summary>Options Settings</summary>
        <div class="bt-row">
          <div class="bt-field">
            <span>Option Type</span>
            <select id="editOptionTypeSelect">
              <option value="">— none —</option>
              <option value="call"${detail.account.optionType === "call" ? " selected" : ""}>call</option>
              <option value="put"${detail.account.optionType === "put" ? " selected" : ""}>put</option>
              <option value="both"${detail.account.optionType === "both" ? " selected" : ""}>both</option>
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

      <div class="edit-params-actions">
        <button id="editParamsSaveBtn" type="button">Save</button>
        <button id="editParamsCancelBtn" type="button">Cancel</button>
        <div id="editParamsMsg"></div>
      </div>
    </div>

    <article>
      <h4>Latest Backtest</h4>
      ${latestBacktest}
    </article>

    <div class="detail-grid">
      <article>
        <h4>Equity Snapshots</h4>
        <table>
          <thead><tr><th>Time</th><th>Equity</th><th>Cash</th><th>Market Value</th></tr></thead>
          <tbody>${snapRows || `<tr><td colspan="4">No snapshots yet.</td></tr>`}</tbody>
        </table>
      </article>

      <article>
        <h4>Recent Trades</h4>
        <div class="table-pagination">
          <button id="recentTradesPrevBtn" type="button" ${tradePage <= 1 ? "disabled" : ""}>Newer</button>
          <span>${viewedStart} to ${viewedEnd} of ${totalTrades}</span>
          <button id="recentTradesNextBtn" type="button" ${tradePage >= totalTradePages ? "disabled" : ""}>Older</button>
        </div>
        <table class="recent-trades-table">
          <thead><tr><th>Time</th><th>Ticker</th><th>Side</th><th>Qty</th><th>Price</th><th>Fee</th></tr></thead>
          <tbody>${tradeRows || `<tr><td colspan="6">No trades yet.</td></tr>`}</tbody>
        </table>
      </article>
    </div>
  `;
}
