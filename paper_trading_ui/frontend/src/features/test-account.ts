import { find } from "../lib/dom";
import { esc } from "../lib/format";
import { getJson, patchJson, postJson } from "../lib/http";
import { renderDetail } from "../components/detail";
import type { AccountDetail, AccountParamsUpdate, ManualTradeRequest } from "../types";

// Must match paper_trading_ui/backend/config.py::TEST_ACCOUNT_NAME
const TEST_ACCOUNT_NAME = "test_account" as const;

export interface TestAccountFeature {
  load: () => Promise<void>;
  wireActions: () => void;
}

function isTradeSide(value: string): value is "buy" | "sell" {
  return value === "buy" || value === "sell";
}

export function createTestAccountFeature(): TestAccountFeature {
  let currentDetail: AccountDetail | null = null;
  let tradePage = 1;
  const tradePageSize = 20;

  function renderCurrentDetail(): void {
    const target = find<HTMLDivElement>("#test-account-detail");
    if (!target || !currentDetail) return;

    target.innerHTML = renderDetail(currentDetail, { tradePage, tradePageSize });

    find<HTMLButtonElement>("#recentTradesPrevBtn")?.addEventListener("click", () => {
      tradePage = Math.max(1, tradePage - 1);
      renderCurrentDetail();
    });

    find<HTMLButtonElement>("#recentTradesNextBtn")?.addEventListener("click", () => {
      if (!currentDetail) return;
      const totalPages = Math.max(1, Math.ceil(currentDetail.trades.length / tradePageSize));
      tradePage = Math.min(totalPages, tradePage + 1);
      renderCurrentDetail();
    });

    find<HTMLButtonElement>("#editParamsBtn")?.addEventListener("click", () => {
      const panel = find<HTMLDivElement>("#editParamsPanel");
      if (panel) panel.hidden = !panel.hidden;
    });

    find<HTMLButtonElement>("#editParamsCancelBtn")?.addEventListener("click", () => {
      const panel = find<HTMLDivElement>("#editParamsPanel");
      if (panel) panel.hidden = true;
    });

    find<HTMLButtonElement>("#editParamsSaveBtn")?.addEventListener("click", () => {
      void saveParams();
    });
  }

  async function saveParams(): Promise<void> {
    if (!currentDetail) return;
    const msgEl = find<HTMLDivElement>("#editParamsMsg");

    const readStr = (id: string) => find<HTMLInputElement>(id)?.value.trim() || undefined;
    const readNum = (id: string): number | null | undefined => {
      const v = find<HTMLInputElement>(id)?.value.trim();
      if (v === undefined || v === "") return undefined;
      const n = parseFloat(v);
      return Number.isFinite(n) ? n : undefined;
    };
    const readInt = (id: string): number | null | undefined => {
      const v = find<HTMLInputElement>(id)?.value.trim();
      if (v === undefined || v === "") return undefined;
      const n = parseInt(v, 10);
      return Number.isFinite(n) ? n : undefined;
    };

    const payload: AccountParamsUpdate = {
      strategy: readStr("#editStrategyInput"),
      descriptiveName: readStr("#editDisplayNameInput"),
      riskPolicy: find<HTMLSelectElement>("#editRiskPolicySelect")?.value || undefined,
      instrumentMode: find<HTMLSelectElement>("#editInstrumentModeSelect")?.value || undefined,
      stopLossPct: readNum("#editStopLossPctInput"),
      takeProfitPct: readNum("#editTakeProfitPctInput"),
      learningEnabled: find<HTMLSelectElement>("#editLearningEnabledSelect")?.value === "true",
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
    };

    try {
      await patchJson<{ status: string }>(
        `/api/accounts/${encodeURIComponent(TEST_ACCOUNT_NAME)}/params`,
        payload,
      );
      if (msgEl) {
        msgEl.className = "";
        msgEl.textContent = "Saved.";
      }
      setTimeout(() => {
        void load();
      }, 800);
    } catch (err) {
      if (msgEl) {
        msgEl.className = "error";
        msgEl.textContent = err instanceof Error ? err.message : "Save failed.";
      }
    }
  }

  async function load(): Promise<void> {
    const target = find<HTMLDivElement>("#test-account-detail");
    if (!target) return;

    target.innerHTML = `<div class="empty">Loading…</div>`;
    try {
      currentDetail = await getJson<AccountDetail>(
        `/api/accounts/${encodeURIComponent(TEST_ACCOUNT_NAME)}`,
      );
      tradePage = 1;
      renderCurrentDetail();
    } catch (err) {
      target.innerHTML = `<div class="error">${esc(err instanceof Error ? err.message : "Load failed.")}</div>`;
    }
  }

  async function onTradeSubmit(event: Event): Promise<void> {
    event.preventDefault();
    const form = event.currentTarget as HTMLFormElement;
    const resultEl = find<HTMLDivElement>("#test-account-trade-result");

    const data = new FormData(form);
    const ticker = ((data.get("ticker") as string | null) ?? "").trim().toUpperCase();
    const sideRaw = ((data.get("side") as string | null) ?? "").trim();
    const qtyRaw = parseFloat((data.get("qty") as string | null) ?? "");
    const priceRaw = parseFloat((data.get("price") as string | null) ?? "");
    const feeRaw = parseFloat((data.get("fee") as string | null) ?? "0");

    if (!ticker || !isTradeSide(sideRaw) || !Number.isFinite(qtyRaw) || !Number.isFinite(priceRaw)) {
      if (resultEl) {
        resultEl.className = "error";
        resultEl.textContent = "Please fill in all required fields correctly.";
      }
      return;
    }

    const payload: ManualTradeRequest = {
      ticker,
      side: sideRaw,
      qty: qtyRaw,
      price: priceRaw,
      fee: Number.isFinite(feeRaw) ? feeRaw : 0,
    };

    if (resultEl) {
      resultEl.className = "";
      resultEl.textContent = "Saving…";
    }

    try {
      await postJson<{ status: string }>(
        `/api/accounts/${encodeURIComponent(TEST_ACCOUNT_NAME)}/trades`,
        payload,
      );
      if (resultEl) {
        resultEl.className = "success";
        resultEl.textContent = `Saved: ${payload.side.toUpperCase()} ${payload.qty} \u00d7 ${esc(payload.ticker)} @ $${payload.price.toFixed(2)}`;
      }
      form.reset();
      await load();
    } catch (err) {
      if (resultEl) {
        resultEl.className = "error";
        resultEl.textContent = err instanceof Error ? err.message : "Trade failed.";
      }
    }
  }

  function wireActions(): void {
    const form = find<HTMLFormElement>("#test-account-trade-form");
    form?.addEventListener("submit", (event) => {
      void onTradeSubmit(event);
    });

    // Lazy-load whenever the tab is opened.
    const tabBtn = find<HTMLButtonElement>('[data-tab="test-account"]');
    tabBtn?.addEventListener("click", () => {
      void load();
    });
  }

  return { load, wireActions };
}
