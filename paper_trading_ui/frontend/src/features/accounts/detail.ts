import { find, findAll } from "../../lib/dom";
import { errorMessage, patchJson, postJson } from "../../lib/http";
import { parseRunId } from "../../lib/parse";
import { TEST_ACCOUNT_NAME } from "../../lib/constants";
import { renderAnalysisPanel, renderDetail } from "../../components/detail";
import type { AccountParamsUpdate } from "../../types";
import type { AccountsFeatureOptions, AccountsState, DetailSection, LoadAccountDetailOptions } from "./types";

function bindClick<T extends Element>(selector: string, handler: (element: T) => Promise<void> | void): void {
  const element = find<T>(selector);
  if (!element) return;
  element.addEventListener("click", () => {
    void handler(element);
  });
}

function buildParamsPayload(): AccountParamsUpdate {
  const readStr = (id: string) => find<HTMLInputElement>(id)?.value.trim() || undefined;
  const readNum = (id: string): number | null | undefined => {
    const value = find<HTMLInputElement>(id)?.value.trim();
    if (value === undefined || value === "") return undefined;
    const parsed = parseFloat(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  };
  const readInt = (id: string): number | null | undefined => {
    const value = find<HTMLInputElement>(id)?.value.trim();
    if (value === undefined || value === "") return undefined;
    const parsed = parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : undefined;
  };
  const readCsv = (id: string): string[] | undefined => {
    const input = find<HTMLInputElement>(id);
    if (!input) return undefined;
    const value = input.value.trim();
    if (!value) return [];
    return value
      .split(",")
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
  };

  return {
    strategy: readStr("#editStrategyInput"),
    descriptiveName: readStr("#editDisplayNameInput"),
    riskPolicy: find<HTMLSelectElement>("#editRiskPolicySelect")?.value || undefined,
    instrumentMode: find<HTMLSelectElement>("#editInstrumentModeSelect")?.value || undefined,
    stopLossPct: readNum("#editStopLossPctInput"),
    takeProfitPct: readNum("#editTakeProfitPctInput"),
    learningEnabled: (() => {
      const el = find<HTMLSelectElement>("#editLearningEnabledSelect");
      return el ? el.value === "true" : undefined;
    })(),
    goalMinReturnPct: readNum("#editGoalMinReturnInput"),
    goalMaxReturnPct: readNum("#editGoalMaxReturnInput"),
    goalPeriod: readStr("#editGoalPeriodInput"),
    optionType: find<HTMLSelectElement>("#editOptionTypeSelect")?.value || undefined,
    optionStrikeOffsetPct: readNum("#editOptionStrikeOffsetInput"),
    optionMinDte: readInt("#editOptionMinDteInput"),
    optionMaxDte: readInt("#editOptionMaxDteInput"),
    targetDeltaMin: readNum("#editTargetDeltaMinInput"),
    targetDeltaMax: readNum("#editTargetDeltaMaxInput"),
    ivRankMin: readNum("#editIvRankMinInput"),
    ivRankMax: readNum("#editIvRankMaxInput"),
    maxPremiumPerTrade: readNum("#editMaxPremiumInput"),
    maxContractsPerTrade: readInt("#editMaxContractsInput"),
    rollDteThreshold: readInt("#editRollDteThresholdInput"),
    profitTakePct: readNum("#editProfitTakePctInput"),
    maxLossPct: readNum("#editMaxLossPctInput"),
    rotationEnabled: (() => {
      const el = find<HTMLSelectElement>("#editRotationEnabledSelect");
      return el ? el.value === "true" : undefined;
    })(),
    rotationMode: find<HTMLSelectElement>("#editRotationModeSelect")?.value || undefined,
    rotationOptimalityMode: find<HTMLSelectElement>("#editRotationOptimalityModeSelect")?.value || undefined,
    rotationIntervalDays: readInt("#editRotationIntervalDaysInput"),
    rotationIntervalMinutes: readInt("#editRotationIntervalMinutesInput"),
    rotationLookbackDays: readInt("#editRotationLookbackDaysInput"),
    rotationSchedule: readCsv("#editRotationScheduleInput"),
    rotationRegimeStrategyRiskOn: readStr("#editRotationRegimeRiskOnInput"),
    rotationRegimeStrategyNeutral: readStr("#editRotationRegimeNeutralInput"),
    rotationRegimeStrategyRiskOff: readStr("#editRotationRegimeRiskOffInput"),
    rotationOverlayMode: find<HTMLSelectElement>("#editRotationOverlayModeSelect")?.value || undefined,
    rotationOverlayMinTickers: readInt("#editRotationOverlayMinTickersInput"),
    rotationOverlayConfidenceThreshold: readNum("#editRotationOverlayConfidenceThresholdInput"),
    rotationOverlayWatchlist: readCsv("#editRotationOverlayWatchlistInput"),
    rotationActiveIndex: readInt("#editRotationActiveIndexInput"),
    rotationLastAt: readStr("#editRotationLastAtInput"),
    rotationActiveStrategy: readStr("#editRotationActiveStrategyInput"),
  };
}

function isDetailSection(section: string | undefined): section is DetailSection {
  return section === "summary"
    || section === "analysis"
    || section === "positions"
    || section === "trades"
    || section === "snapshots"
    || section === "config";
}

export function applyCachedAnalysis(state: AccountsState): void {
  if (!state.currentAnalysis) {
    return;
  }
  const panel = find<HTMLElement>("#analysisPanel");
  if (panel) {
    panel.innerHTML = renderAnalysisPanel(state.currentAnalysis);
  }
}

export function renderCurrentDetail(
  state: AccountsState,
  options: AccountsFeatureOptions,
  handlers: {
    loadAccounts: () => Promise<void>;
    loadAccountDetail: (accountName: string, options?: LoadAccountDetailOptions) => Promise<void>;
  },
): void {
  const target = find<HTMLDivElement>("#accountDetail");
  if (!target || !state.currentDetail) return;

  target.innerHTML = renderDetail(state.currentDetail, {
    activeSection: state.currentDetailSection,
    tradePage: state.currentTradePage,
    tradePageSize: state.tradePageSize,
    showAddTrade: state.currentDetail.account.name === TEST_ACCOUNT_NAME,
  });

  bindClick<HTMLButtonElement>("#snapshotOneBtn", async (button) => {
    const accountName = button.dataset.account;
    if (!accountName) return;
    await postJson(`/api/actions/snapshot/${encodeURIComponent(accountName)}`);
    await handlers.loadAccountDetail(accountName, { section: state.currentDetailSection });
    await handlers.loadAccounts();
  });

  bindClick<HTMLButtonElement>("#openLatestBacktestReportBtn", async (button) => {
    const runId = parseRunId(button.dataset.runId);
    if (runId === null) return;
    await options.onOpenRunReport?.(runId);
  });

  bindClick<HTMLButtonElement>("#recentTradesPrevBtn", () => {
    state.currentTradePage = Math.max(1, state.currentTradePage - 1);
    renderCurrentDetail(state, options, handlers);
  });

  bindClick<HTMLButtonElement>("#recentTradesNextBtn", () => {
    if (!state.currentDetail) return;
    const totalPages = Math.max(1, Math.ceil(state.currentDetail.trades.length / state.tradePageSize));
    state.currentTradePage = Math.min(totalPages, state.currentTradePage + 1);
    renderCurrentDetail(state, options, handlers);
  });

  bindClick<HTMLButtonElement>("#addTradeBtn", () => {
    const panel = find<HTMLDivElement>("#addTradePanel");
    if (panel) panel.hidden = !panel.hidden;
  });

  bindClick<HTMLButtonElement>("#addTradeCancelBtn", () => {
    const panel = find<HTMLDivElement>("#addTradePanel");
    if (panel) panel.hidden = true;
  });

  bindClick<HTMLButtonElement>("#addTradeSaveBtn", async () => {
    if (!state.currentDetail) return;
    const accountName = state.currentDetail.account.name;
    const msgEl = find<HTMLDivElement>("#addTradeMsg");
    const ticker = find<HTMLInputElement>("#addTradeTicker")?.value.trim().toUpperCase();
    const side = find<HTMLSelectElement>("#addTradeSide")?.value;
    const qty = parseFloat(find<HTMLInputElement>("#addTradeQty")?.value ?? "");
    const price = parseFloat(find<HTMLInputElement>("#addTradePrice")?.value ?? "");
    const fee = parseFloat(find<HTMLInputElement>("#addTradeFee")?.value ?? "0");

    if (!ticker || !side || !Number.isFinite(qty) || qty <= 0 || !Number.isFinite(price) || price <= 0) {
      if (msgEl) {
        msgEl.className = "error";
        msgEl.textContent = "Ticker, qty, and price are required.";
      }
      return;
    }

    try {
      await postJson<{ status: string }>(
        `/api/accounts/${encodeURIComponent(accountName)}/trades`,
        { ticker, side, qty, price, fee: Number.isFinite(fee) ? fee : 0 },
      );
      if (msgEl) {
        msgEl.className = "";
        msgEl.textContent = "Trade added.";
      }
      setTimeout(() => {
        void handlers.loadAccountDetail(accountName, { section: state.currentDetailSection });
      }, 800);
    } catch (err) {
      if (msgEl) {
        msgEl.className = "error";
        msgEl.textContent = errorMessage(err, "Failed to add trade.");
      }
    }
  });

  bindClick<HTMLButtonElement>("#openConfigBtn", () => {
    state.currentDetailSection = "config";
    renderCurrentDetail(state, options, handlers);
    const panel = find<HTMLDivElement>("#editParamsPanel");
    if (panel) panel.hidden = false;
  });

  bindClick<HTMLButtonElement>("#editParamsBtn", () => {
    const panel = find<HTMLDivElement>("#editParamsPanel");
    if (panel) panel.hidden = !panel.hidden;
  });

  bindClick<HTMLButtonElement>("#editParamsCancelBtn", () => {
    const panel = find<HTMLDivElement>("#editParamsPanel");
    if (panel) panel.hidden = true;
  });

  bindClick<HTMLButtonElement>("#editParamsSaveBtn", async () => {
    if (!state.currentDetail) return;
    const accountName = state.currentDetail.account.name;
    const msgEl = find<HTMLDivElement>("#editParamsMsg");

    try {
      await patchJson<{ status: string }>(
        `/api/accounts/${encodeURIComponent(accountName)}/params`,
        buildParamsPayload(),
      );
      if (msgEl) {
        msgEl.className = "";
        msgEl.textContent = "Saved.";
      }
      setTimeout(() => {
        void handlers.loadAccountDetail(accountName, { section: "config" });
      }, 800);
    } catch (err) {
      if (msgEl) {
        msgEl.className = "error";
        msgEl.textContent = errorMessage(err, "Save failed.");
      }
    }
  });

  applyCachedAnalysis(state);

  for (const button of findAll<HTMLButtonElement>(".detail-section-tab")) {
    button.addEventListener("click", () => {
      const section = button.dataset.detailSection;
      if (!isDetailSection(section)) {
        return;
      }
      state.currentDetailSection = section;
      renderCurrentDetail(state, options, handlers);
    });
  }
}
