import { find, findAll } from "../../lib/dom";
import { errorMessage, patchJson, postJson } from "../../lib/http";
import { parseRunId } from "../../lib/parse";
import { renderAnalysisPanel, renderDetail } from "../../components/detail";
import type { AccountParamsUpdate, BookParamsUpdate } from "../../types/accounts";
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
    optionProfitTakePct: readNum("#editOptionProfitTakePctInput"),
    optionMaxLossPct: readNum("#editOptionMaxLossPctInput"),
    rotation: (() => {
      const enabledEl = find<HTMLSelectElement>("#editRotationEnabledSelect");
      const rotation = {
        enabled: enabledEl ? enabledEl.value === "true" : undefined,
        lookbackDays: readInt("#editRotationLookbackDaysInput"),
        schedule: readCsv("#editRotationScheduleInput"),
      };
      const hasAny = rotation.enabled !== undefined
        || rotation.lookbackDays !== undefined
        || rotation.schedule !== undefined;
      return hasAny ? rotation : undefined;
    })(),
  };
}

function isDetailSection(section: string | undefined): section is DetailSection {
  return section === "summary"
    || section === "books"
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
    bookName: state.currentBookFilter,
  });

  find<HTMLSelectElement>("#accountBookFilter")?.addEventListener("change", event => {
    state.currentBookFilter = (event.currentTarget as HTMLSelectElement).value || null;
    state.currentTradePage = 1;
    renderCurrentDetail(state, options, handlers);
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

  bindClick<HTMLButtonElement>("#openConfigBtn", () => {
    const existingPanel = find<HTMLDivElement>("#editParamsPanel");
    const panelOpen = state.currentDetailSection === "config" && !!existingPanel && !existingPanel.hidden;
    if (panelOpen) {
      renderCurrentDetail(state, options, handlers);
      return;
    }
    state.currentDetailSection = "config";
    renderCurrentDetail(state, options, handlers);
    const panel = find<HTMLDivElement>("#editParamsPanel");
    if (panel) panel.hidden = false;
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

  for (const button of findAll<HTMLButtonElement>(".book-config-save")) {
    button.addEventListener("click", async () => {
      const form = button.closest<HTMLFormElement>(".book-config-form");
      const bookName = button.dataset.book;
      if (!form || !bookName || !state.currentDetail) return;
      const data = new FormData(form);
      const number = (name: string): number | undefined => {
        const raw = String(data.get(name) ?? "").trim();
        if (!raw) return undefined;
        const parsed = Number(raw);
        return Number.isFinite(parsed) ? parsed : undefined;
      };
      const csv = (name: string): string[] => String(data.get(name) ?? "")
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
      const payload: BookParamsUpdate = {
        strategy: String(data.get("strategy") ?? "").trim() || undefined,
        riskPolicy: String(data.get("riskPolicy") ?? "") || undefined,
        instrumentMode: String(data.get("instrumentMode") ?? "") || undefined,
        learningEnabled: data.get("learningEnabled") === "true",
        tradeSizePct: number("tradeSizePct"),
        maxPositionPct: number("maxPositionPct"),
        stopLossPct: number("stopLossPct"),
        takeProfitPct: number("takeProfitPct"),
        goalMinReturnPct: number("goalMinReturnPct"),
        goalMaxReturnPct: number("goalMaxReturnPct"),
        goalPeriod: String(data.get("goalPeriod") ?? "").trim() || undefined,
        tradeUniverses: csv("tradeUniverses"),
        maxTradesPerRun: number("maxTradesPerRun"),
        optionType: String(data.get("optionType") ?? "").trim() || undefined,
        optionStrikeOffsetPct: number("optionStrikeOffsetPct"),
        optionMinDte: number("optionMinDte"),
        optionMaxDte: number("optionMaxDte"),
        targetDeltaMin: number("targetDeltaMin"),
        targetDeltaMax: number("targetDeltaMax"),
        maxPremiumPerTrade: number("maxPremiumPerTrade"),
        maxContractsPerTrade: number("maxContractsPerTrade"),
        ivRankMin: number("ivRankMin"),
        ivRankMax: number("ivRankMax"),
        rollDteThreshold: number("rollDteThreshold"),
        optionProfitTakePct: number("optionProfitTakePct"),
        optionMaxLossPct: number("optionMaxLossPct"),
        rotation: {
          enabled: data.get("rotationEnabled") === "true",
          schedule: csv("rotationSchedule"),
          lookbackDays: number("rotationLookbackDays"),
        },
        rotationPolicy: {
          minTradesInWindow: number("minTradesInWindow"),
          outperformanceThresholdBps: number("outperformanceThresholdBps"),
          cooldownDays: number("cooldownDays"),
          riskAdjustedReturnWeight: number("riskAdjustedReturnWeight"),
          stabilityWeight: number("stabilityWeight"),
          drawdownPenaltyWeight: number("drawdownPenaltyWeight"),
        },
      };
      const message = form.querySelector<HTMLElement>(".book-config-message");
      try {
        await patchJson(
          `/api/accounts/${encodeURIComponent(state.currentDetail.account.name)}/books/${encodeURIComponent(bookName)}/params`,
          payload,
        );
        if (message) message.textContent = "Saved.";
        await handlers.loadAccountDetail(state.currentDetail.account.name, { section: "books" });
      } catch (err) {
        if (message) {
          message.className = "book-config-message error";
          message.textContent = errorMessage(err, "Save failed.");
        }
      }
    });
  }

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
