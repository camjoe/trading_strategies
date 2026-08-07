import { currency, esc } from "../../lib/format";
import type { AccountDetail, BookConfiguration } from "../../types/accounts";
import type { DetailSectionName } from "./types";

function input(name: string, label: string, value: string | number | null, type = "number"): string {
  return `<label class="bt-field"><span>${label}</span><input name="${name}" type="${type}" value="${esc(String(value ?? ""))}" /></label>`;
}

function bookEditor(book: BookConfiguration): string {
  const rotation = book.rotation;
  const policy = book.rotationPolicy;
  return `
    <details class="edit-params-section">
      <summary>Edit ${esc(book.name)}</summary>
      <form class="book-config-form">
        <div class="bt-row">
          ${input("strategy", "Strategy", book.strategy, "text")}
          ${input("tradeUniverses", "Set universes (names)", "", "text")}
          ${input("goalPeriod", "Goal period", book.goalPeriod, "text")}
        </div>
        <div class="bt-row">
          <label class="bt-field"><span>Status</span><input value="${esc(book.status)}" disabled /></label>
          <label class="bt-field"><span>Risk policy</span><select name="riskPolicy">
            ${["none", "fixed_stop", "take_profit", "stop_and_target"].map(value => `<option value="${value}"${value === book.riskPolicy ? " selected" : ""}>${value}</option>`).join("")}
          </select></label>
          <label class="bt-field"><span>Instrument mode</span><select name="instrumentMode">
            ${["equity", "leaps"].map(value => `<option value="${value}"${value === book.instrumentMode ? " selected" : ""}>${value}</option>`).join("")}
          </select></label>
          <label class="bt-field"><span>Learning</span><select name="learningEnabled">
            <option value="false"${!book.learningEnabled ? " selected" : ""}>Off</option>
            <option value="true"${book.learningEnabled ? " selected" : ""}>On</option>
          </select></label>
        </div>
        <div class="bt-row">
          ${input("tradeSizePct", "Trade size", book.tradeSizePct)}
          ${input("maxPositionPct", "Max position", book.maxPositionPct)}
          ${input("stopLossPct", "Stop loss %", book.stopLossPct)}
          ${input("takeProfitPct", "Take profit %", book.takeProfitPct)}
          ${input("goalMinReturnPct", "Goal min %", book.goalMinReturnPct)}
          ${input("goalMaxReturnPct", "Goal max %", book.goalMaxReturnPct)}
          ${input("maxTradesPerRun", "Max trades / run", book.maxTradesPerRun)}
        </div>
        <details class="bt-advanced">
          <summary>Options settings</summary>
          <div class="bt-advanced-body">
            <div class="bt-row">
              ${input("optionType", "Option type", book.optionType, "text")}
              ${input("optionStrikeOffsetPct", "Strike offset %", book.optionStrikeOffsetPct)}
              ${input("optionMinDte", "Minimum DTE", book.optionMinDte)}
              ${input("optionMaxDte", "Maximum DTE", book.optionMaxDte)}
              ${input("targetDeltaMin", "Target delta min", book.targetDeltaMin)}
              ${input("targetDeltaMax", "Target delta max", book.targetDeltaMax)}
            </div>
            <div class="bt-row">
              ${input("maxPremiumPerTrade", "Max premium", book.maxPremiumPerTrade)}
              ${input("maxContractsPerTrade", "Max contracts", book.maxContractsPerTrade)}
              ${input("ivRankMin", "IV rank min", book.ivRankMin)}
              ${input("ivRankMax", "IV rank max", book.ivRankMax)}
              ${input("rollDteThreshold", "Roll DTE", book.rollDteThreshold)}
              ${input("optionProfitTakePct", "Profit take %", book.optionProfitTakePct)}
              ${input("optionMaxLossPct", "Max loss %", book.optionMaxLossPct)}
            </div>
          </div>
        </details>
        <div class="bt-row">
          <label class="bt-field"><span>Rotation enabled</span><select name="rotationEnabled">
            <option value="false"${!rotation.enabled ? " selected" : ""}>Off</option>
            <option value="true"${rotation.enabled ? " selected" : ""}>On</option>
          </select></label>
          ${input("rotationSchedule", "Challenger schedule", (rotation.schedule ?? []).join(","), "text")}
          ${input("rotationLookbackDays", "Lookback days", rotation.lookbackDays ?? null)}
          ${input("minTradesInWindow", "Minimum trades", policy.minTradesInWindow)}
          ${input("outperformanceThresholdBps", "Threshold (bps)", policy.outperformanceThresholdBps)}
          ${input("cooldownDays", "Cooldown days", policy.cooldownDays)}
        </div>
        <div class="bt-row">
          ${input("riskAdjustedReturnWeight", "Return weight", policy.riskAdjustedReturnWeight)}
          ${input("stabilityWeight", "Stability weight", policy.stabilityWeight)}
          ${input("drawdownPenaltyWeight", "Drawdown weight", policy.drawdownPenaltyWeight)}
          ${input("regimeFitWeight", "Regime fit weight", policy.regimeFitWeight)}
        </div>
        <div class="edit-params-actions">
          <button class="book-config-save" data-book="${esc(book.name)}" type="button">Save book</button>
          <span class="book-config-message"></span>
        </div>
      </form>
    </details>`;
}

export function renderBooksSection(activeSection: DetailSectionName, detail: AccountDetail): string {
  const cards = (detail.books ?? []).map(book => `
    <section class="config-summary-card">
      <h5>${esc(book.name)} ${book.isDefault ? '<span class="chip">default</span>' : ""}</h5>
      <div class="analysis-summary">
        <div class="analysis-stat"><span class="label">Strategy</span><span>${esc(book.strategy)}</span></div>
        <div class="analysis-stat"><span class="label">Status</span><span>${esc(book.status)}</span></div>
        <div class="analysis-stat"><span class="label">Equity</span><span>${currency.format(book.currentEquity)}</span></div>
        <div class="analysis-stat"><span class="label">Cash</span><span>${currency.format(book.currentCash)}</span></div>
        <div class="analysis-stat"><span class="label">Symbols</span><span>${esc(book.tradeSymbols.join(", "))}</span></div>
        <div class="analysis-stat"><span class="label">Rotation</span><span>${book.rotation.enabled ? "On" : "Off"}</span></div>
      </div>
      ${bookEditor(book)}
    </section>`).join("");
  return `<article class="detail-section-panel" data-detail-panel="books" ${activeSection === "books" ? "" : "hidden"}>
    <div class="config-section-head"><div><h4>Strategy Books</h4><p class="muted">Inspect and edit the settings owned by each execution book.</p></div></div>
    <div class="config-summary-stack">${cards || '<div class="empty">No books configured.</div>'}</div>
  </article>`;
}
