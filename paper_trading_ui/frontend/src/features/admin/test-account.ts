import { find } from "../../lib/dom";
import { esc } from "../../lib/format";
import { errorMessage, postJson } from "../../lib/http";
import { TEST_ACCOUNT_NAME } from "../../lib/constants";


export interface AdminTestAccountController {
  wireActions: () => void;
}


function isTradeSide(value: string): value is "buy" | "sell" {
  return value === "buy" || value === "sell";
}


export function createAdminTestAccountController(): AdminTestAccountController {
  async function onTestTradeSubmit(event: Event): Promise<void> {
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

    const payload = {
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
        resultEl.textContent = `Saved: ${payload.side.toUpperCase()} ${payload.qty} × ${esc(payload.ticker)} @ $${payload.price.toFixed(2)}`;
      }
      form.reset();
    } catch (err) {
      if (resultEl) {
        resultEl.className = "error";
        resultEl.textContent = errorMessage(err, "Trade failed.");
      }
    }
  }

  function wireActions(): void {
    const testTradeForm = find<HTMLFormElement>("#test-account-trade-form");
    testTradeForm?.addEventListener("submit", (event) => {
      void onTestTradeSubmit(event);
    });
  }

  return {
    wireActions,
  };
}
