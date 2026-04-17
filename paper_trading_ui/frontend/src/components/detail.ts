import { currency, esc } from "../lib/format";
import { getAccountConfigOptions, renderOptionTags } from "../lib/account-config-options";
import type { AccountAnalysis, AccountDetail } from "../types";

export interface DetailRenderOptions {
  tradePage?: number;
  tradePageSize?: number;
  activeSection?: "summary" | "positions" | "trades" | "snapshots";
  /** Show Edit Parameters, Snapshot buttons + edit panel. Default: true. */
  showActions?: boolean;
  /** Show the Add Trade button and panel. Should only be true for test_account. Default: false. */
  showAddTrade?: boolean;
  /** Show the Latest Backtest report section. Default: true. */
  showBacktest?: boolean;
}

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

function tradeTypeBadge(note: string | null): string {
  if (!note) return `<span class="chip chip--equity">equity</span>`;
  if (note.includes("instrument=option")) return `<span class="chip chip--option">option</span>`;
  if (note.includes("auto-daily")) return `<span class="chip chip--auto">auto</span>`;
  return `<span class="chip chip--manual">manual</span>`;
}

function metricValue(value: number | null | undefined, suffix = "", digits = 2): string {
  return value == null ? "—" : `${value.toFixed(digits)}${suffix}`;
}

function renderEquitySparkline(
  snapshots: AccountDetail["snapshots"],
  options: { title: string },
): string {
  const { title } = options;
  if (snapshots.length < 2) {
    return `<div class="muted">${esc(title)} unavailable.</div>`;
  }

  const equities = snapshots.map((item) => item.equity);
  const minEquity = Math.min(...equities);
  const maxEquity = Math.max(...equities);
  const spread = Math.max(maxEquity - minEquity, 1);
  const width = 320;
  const height = 96;
  const pad = 8;
  const points = snapshots
    .map((item, index) => {
      const x = pad + ((width - (pad * 2)) * index) / Math.max(snapshots.length - 1, 1);
      const y = height - pad - (((item.equity - minEquity) / spread) * (height - (pad * 2)));
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return `
    <div class="bt-equity-curve">
      <div class="row slim"><strong>${esc(title)}</strong> <span>${currency.format(minEquity)} to ${currency.format(maxEquity)}</span></div>
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(title)}">
        <polyline fill="none" stroke="currentColor" stroke-width="2" points="${points}" />
      </svg>
    </div>
  `;
}

function renderBenchmarkOverlaySparkline(overlay: NonNullable<AccountDetail["liveBenchmarkOverlay"]>): string {
  if (overlay.points.length < 2) {
    return `<div class="muted">Benchmark overlay unavailable.</div>`;
  }

  const values = overlay.points.flatMap((item) => [item.accountEquity, item.benchmarkEquity]);
  const minEquity = Math.min(...values);
  const maxEquity = Math.max(...values);
  const spread = Math.max(maxEquity - minEquity, 1);
  const width = 320;
  const height = 96;
  const pad = 8;
  const pointFor = (value: number, index: number): string => {
    const x = pad + ((width - (pad * 2)) * index) / Math.max(overlay.points.length - 1, 1);
    const y = height - pad - (((value - minEquity) / spread) * (height - (pad * 2)));
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  };
  const accountPoints = overlay.points
    .map((item, index) => pointFor(item.accountEquity, index))
    .join(" ");
  const benchmarkPoints = overlay.points
    .map((item, index) => pointFor(item.benchmarkEquity, index))
    .join(" ");

  return `
    <div class="bt-equity-curve">
      <div class="row slim">
        <strong>Live vs ${esc(overlay.benchmark)}</strong>
        <span>Account ${overlay.accountReturnPct.toFixed(2)}% | Benchmark ${overlay.benchmarkReturnPct.toFixed(2)}% | Alpha ${overlay.alphaPct.toFixed(2)}%</span>
      </div>
      <div class="row slim">
        <span>Account line</span>
        <span style="color:#6b7280">Benchmark line</span>
      </div>
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Live vs ${esc(overlay.benchmark)}">
        <polyline fill="none" stroke="currentColor" stroke-width="2" points="${accountPoints}" />
        <polyline fill="none" stroke="#6b7280" stroke-width="2" stroke-dasharray="4 3" points="${benchmarkPoints}" />
      </svg>
    </div>
  `;
}

export function renderDetail(detail: AccountDetail, options: DetailRenderOptions = {}): string {
  const tradePageSize = Math.max(1, options.tradePageSize ?? 20);
  const totalTrades = detail.trades.length;
  const totalTradePages = Math.max(1, Math.ceil(totalTrades / tradePageSize));
  const tradePage = Math.min(Math.max(1, options.tradePage ?? 1), totalTradePages);
  const showActions = options.showActions !== false;
  const showAddTrade = options.showAddTrade === true;
  const showBacktest = options.showBacktest !== false;
  const activeSection = options.activeSection ?? "summary";
  const viewedStart = totalTrades === 0 ? 0 : (tradePage - 1) * tradePageSize + 1;
  const viewedEnd = totalTrades === 0 ? 0 : Math.min(tradePage * tradePageSize, totalTrades);
  const sectionTabs: Array<{ id: typeof activeSection; label: string }> = [
    { id: "summary", label: "Summary" },
    { id: "positions", label: "Positions" },
    { id: "trades", label: "Trades" },
    { id: "snapshots", label: "Snapshots" },
  ];

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
        <td>${tradeTypeBadge(t.note)}</td>
        <td>${t.qty.toFixed(2)}</td>
        <td>${currency.format(t.price)}</td>
        <td>${currency.format(t.qty * t.price)}</td>
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
        ${detail.latestBacktestMetrics
          ? `<div class="analysis-summary">
              <div class="analysis-stat"><span class="label">Backtest Return</span><span>${metricValue(detail.latestBacktestMetrics.totalReturnPct, "%")}</span></div>
              <div class="analysis-stat"><span class="label">Max DD</span><span>${metricValue(detail.latestBacktestMetrics.maxDrawdownPct, "%")}</span></div>
              <div class="analysis-stat"><span class="label">Sharpe</span><span>${metricValue(detail.latestBacktestMetrics.sharpeRatio)}</span></div>
              <div class="analysis-stat"><span class="label">Win Rate</span><span>${metricValue(detail.latestBacktestMetrics.winRatePct, "%")}</span></div>
              <div class="analysis-stat"><span class="label">Profit Factor</span><span>${metricValue(detail.latestBacktestMetrics.profitFactor)}</span></div>
            </div>`
          : ""}
        <button id="openLatestBacktestReportBtn" data-run-id="${detail.latestBacktest.runId}" type="button">Open Report</button>
      </div>
    `
    : `<div class="empty">No backtest run found for this account yet.</div>`;
  const benchmarkSummary = detail.liveBenchmarkOverlay
    ? `<div class="analysis-summary">
         <div class="analysis-stat"><span class="label">Benchmark Return</span><span>${metricValue(detail.liveBenchmarkOverlay.benchmarkReturnPct, "%")}</span></div>
         <div class="analysis-stat"><span class="label">Live Alpha</span><span>${metricValue(detail.liveBenchmarkOverlay.alphaPct, "%")}</span></div>
         <div class="analysis-stat"><span class="label">Benchmark Equity</span><span>${currency.format(detail.liveBenchmarkOverlay.benchmarkEquity)}</span></div>
       </div>`
    : "";

  return `
    <div class="detail-head">
      <div>
        <h3>${esc(detail.account.displayName)}</h3>
        <p>${esc(detail.account.name)} | ${esc(detail.account.strategy)} | ${esc(detail.account.benchmark)}</p>
        <p class="row slim">
          Equity: <strong>${currency.format(detail.account.equity)}</strong>
          &nbsp;·&nbsp; Settlement Cash: <strong>${currency.format(detail.account.settlementCash)}</strong>
          &nbsp;·&nbsp; Return: <span class="${detail.account.totalChangePct >= 0 ? "up" : "down"}">${detail.account.totalChangePct >= 0 ? "+" : ""}${detail.account.totalChangePct.toFixed(2)}%</span>
        </p>
        ${benchmarkSummary}
      </div>
      ${showActions || showAddTrade ? `<div class="detail-head-actions">
        ${showAddTrade ? `<button id="addTradeBtn" type="button">+ Add Trade</button>` : ""}
        ${showActions ? `<button id="editParamsBtn" type="button">Edit Parameters</button>
        <button id="snapshotOneBtn" type="button" data-account="${esc(detail.account.name)}">Snapshot This Account</button>` : ""}
      </div>` : ""}
    </div>

    <div class="detail-section-tabs" role="tablist" aria-label="Account workspace sections">
      ${sectionTabs
        .map(
          (section) => `
            <button
              type="button"
              class="detail-section-tab${section.id === activeSection ? " active" : ""}"
              data-detail-section="${section.id}"
              aria-selected="${String(section.id === activeSection)}"
            >
              ${section.label}
            </button>
          `,
        )
        .join("")}
    </div>

    ${showAddTrade ? `<div id="addTradePanel" class="edit-params-panel" hidden>
      <div class="edit-params-section">
        <h5>Add Trade</h5>
        <div class="bt-row">
          <div class="bt-field">
            <span>Ticker</span>
            <input id="addTradeTicker" type="text" placeholder="e.g. AAPL" style="text-transform:uppercase" />
          </div>
          <div class="bt-field">
            <span>Side</span>
            <select id="addTradeSide">
              <option value="buy">buy</option>
              <option value="sell">sell</option>
            </select>
          </div>
          <div class="bt-field">
            <span>Qty</span>
            <input id="addTradeQty" type="number" step="0.0001" min="0.0001" placeholder="e.g. 10" />
          </div>
          <div class="bt-field">
            <span>Price</span>
            <input id="addTradePrice" type="number" step="0.01" min="0.01" placeholder="e.g. 150.00" />
          </div>
          <div class="bt-field">
            <span>Fee</span>
            <input id="addTradeFee" type="number" step="0.01" min="0" value="0" />
          </div>
        </div>
      </div>
      <div class="edit-params-actions">
        <button id="addTradeSaveBtn" type="button">Submit Trade</button>
        <button id="addTradeCancelBtn" type="button">Cancel</button>
        <div id="addTradeMsg"></div>
      </div>
    </div>` : ""}

    ${showActions ? `<div id="editParamsPanel" class="edit-params-panel" hidden>
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
    </div>` : ""}

    <article class="detail-section-panel" data-detail-panel="summary" ${activeSection === "summary" ? "" : "hidden"}>
      <div id="analysisPanel">
        <h4>Performance Analysis</h4>
        <div class="empty">Loading analysis…</div>
      </div>
      ${showBacktest ? `<div class="latest-backtest-section">
        <h4>Latest Backtest</h4>
        ${latestBacktest}
      </div>` : ""}
    </article>

    <article class="detail-section-panel" data-detail-panel="positions" ${activeSection === "positions" ? "" : "hidden"}>
      <h4>Current Positions</h4>
      <table>
        <thead><tr><th>Ticker</th><th>Qty</th><th>Avg Cost</th><th>Market Price</th><th>Market Value</th><th>Unrealized P&amp;L</th></tr></thead>
        <tbody>${
          detail.positions.length === 0
            ? `<tr><td colspan="6">No open positions.</td></tr>`
            : detail.positions
                .map(
                  (p) => `
          <tr>
            <td><strong>${esc(p.ticker)}</strong></td>
            <td>${p.qty.toFixed(2)}</td>
            <td>${currency.format(p.avgCost)}</td>
            <td>${p.marketPrice > 0 ? currency.format(p.marketPrice) : "—"}</td>
            <td>${p.marketPrice > 0 ? currency.format(p.marketValue) : "—"}</td>
            <td class="${p.unrealizedPnl >= 0 ? "up" : "down"}">${p.marketPrice > 0 ? currency.format(p.unrealizedPnl) : "—"}</td>
          </tr>
        `,
                )
                .join("")
        }</tbody>
      </table>
    </article>

    <article class="detail-section-panel" data-detail-panel="trades" ${activeSection === "trades" ? "" : "hidden"}>
      <h4>Recent Trades</h4>
      <div class="table-pagination">
        <button id="recentTradesPrevBtn" type="button" ${tradePage <= 1 ? "disabled" : ""}>Newer</button>
        <span>${viewedStart} to ${viewedEnd} of ${totalTrades}</span>
        <button id="recentTradesNextBtn" type="button" ${tradePage >= totalTradePages ? "disabled" : ""}>Older</button>
      </div>
      <table class="recent-trades-table">
        <thead><tr><th>Time</th><th>Ticker</th><th>Side</th><th>Type</th><th>Qty</th><th>Price</th><th>Total</th></tr></thead>
        <tbody>${tradeRows || `<tr><td colspan="7">No trades yet.</td></tr>`}</tbody>
      </table>
    </article>

    <article class="detail-section-panel" data-detail-panel="snapshots" ${activeSection === "snapshots" ? "" : "hidden"}>
      <h4>Equity Snapshots</h4>
      ${detail.liveBenchmarkOverlay
        ? renderBenchmarkOverlaySparkline(detail.liveBenchmarkOverlay)
        : ""}
      ${renderEquitySparkline(detail.snapshots, { title: "Live Equity Curve" })}
      <table>
        <thead><tr><th>Time</th><th>Equity</th><th>Cash</th><th>Market Value</th></tr></thead>
        <tbody>${snapRows || `<tr><td colspan="4">No snapshots yet.</td></tr>`}</tbody>
      </table>
    </article>
  `;
}

export function renderAnalysisPanel(analysis: AccountAnalysis): string {
  const signClass = (v: number) => (v >= 0 ? "up" : "down");
  const pct = (v: number | null) =>
    v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;

  const benchmarkLine =
    analysis.benchmarkReturnPct != null
      ? `<span class="${signClass(analysis.benchmarkReturnPct)}">${pct(analysis.benchmarkReturnPct)}</span>`
      : `<span class="muted">—</span>`;

  const alphaLine =
    analysis.alphaPct != null
      ? `<span class="${signClass(analysis.alphaPct)}">${pct(analysis.alphaPct)} alpha</span>`
      : `<span class="muted">—</span>`;

  const positionRows = (positions: AccountAnalysis["topWinners"]) =>
    positions
      .map(
        (p) => `
        <tr>
          <td><strong>${esc(p.ticker)}</strong></td>
          <td>${currency.format(p.avgCost)}</td>
          <td>${p.marketPrice > 0 ? currency.format(p.marketPrice) : "—"}</td>
          <td class="${signClass(p.unrealizedPnl)}">${p.marketPrice > 0 ? currency.format(p.unrealizedPnl) : "—"}</td>
          <td class="${signClass(p.unrealizedPnlPct)}">${p.marketPrice > 0 ? pct(p.unrealizedPnlPct) : "—"}</td>
        </tr>`,
      )
      .join("");

  const notesList = analysis.improvementNotes
    .map((n) => `<li>${esc(n)}</li>`)
    .join("");

  return `
    <h4>Performance Analysis</h4>
    <div class="analysis-summary">
      <div class="analysis-stat">
        <span class="label">Account Return</span>
        <span class="${signClass(analysis.accountReturnPct)}">${pct(analysis.accountReturnPct)}</span>
      </div>
      <div class="analysis-stat">
        <span class="label">Benchmark (${analysis.benchmarkReturnPct != null ? (analysis.benchmarkTicker ?? "—") : "—"})</span>
        ${benchmarkLine}
      </div>
      <div class="analysis-stat">
        <span class="label">Alpha</span>
        ${alphaLine}
      </div>
      <div class="analysis-stat">
        <span class="label">Realized P&amp;L</span>
        <span class="${signClass(analysis.realizedPnl)}">${currency.format(analysis.realizedPnl)}</span>
      </div>
      <div class="analysis-stat">
        <span class="label">Unrealized P&amp;L</span>
        <span class="${signClass(analysis.unrealizedPnl)}">${currency.format(analysis.unrealizedPnl)}</span>
      </div>
    </div>

    <div class="analysis-tables">
      <div>
        <h5>Top Winners <span class="muted analysis-table-note">(open positions, unrealized)</span></h5>
        <table>
          <thead><tr><th>Ticker</th><th>Avg Cost</th><th>Price</th><th>Unr. P&amp;L</th><th>%</th></tr></thead>
          <tbody>${positionRows(analysis.topWinners) || `<tr><td colspan="5">None</td></tr>`}</tbody>
        </table>
      </div>
      <div>
        <h5>Top Losers <span class="muted analysis-table-note">(open positions, unrealized)</span></h5>
        <table>
          <thead><tr><th>Ticker</th><th>Avg Cost</th><th>Price</th><th>Unr. P&amp;L</th><th>%</th></tr></thead>
          <tbody>${positionRows(analysis.topLosers) || `<tr><td colspan="5">None</td></tr>`}</tbody>
        </table>
      </div>
    </div>

    ${notesList ? `<div class="analysis-notes"><h5>Improvement Notes</h5><ul>${notesList}</ul></div>` : ""}
  `;
}
