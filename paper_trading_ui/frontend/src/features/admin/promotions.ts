import { renderPromotionOverview } from "../../components/admin-ops";
import { find } from "../../lib/dom";
import { errorMessage, getJson } from "../../lib/http";
import type { PromotionOverviewResponse } from "../../types";
import { setHtml, setOutput } from "./ui";


export interface AdminPromotionsController {
  loadPromotionOverview: () => Promise<void>;
  wireActions: () => void;
}


export function createAdminPromotionsController(): AdminPromotionsController {
  async function loadPromotionOverview(): Promise<void> {
    const accountSelect = find<HTMLSelectElement>("#promotionAccountSelect");
    const strategyInput = find<HTMLInputElement>("#promotionStrategyInput");
    const output = find<HTMLDivElement>("#promotionOverviewOutput");
    if (!accountSelect || !output) return;

    if (!accountSelect.value) {
      setOutput(output, "empty", "Select an account to inspect promotion readiness.");
      return;
    }

    setOutput(output, "empty", "Loading promotion status...");
    try {
      const query = new URLSearchParams({ accountName: accountSelect.value, limit: "5" });
      const strategyName = strategyInput?.value.trim() ?? "";
      if (strategyName) {
        query.set("strategyName", strategyName);
      }
      const data = await getJson<PromotionOverviewResponse>(`/api/admin/promotion/overview?${query.toString()}`);
      setHtml(output, "promotion-output", renderPromotionOverview(data));
    } catch (error) {
      setOutput(output, "error", errorMessage(error, "Failed to load promotion readiness."));
    }
  }

  function wireActions(): void {
    const promotionLoadBtn = find<HTMLButtonElement>("#promotionLoadBtn");
    const promotionAccountSelect = find<HTMLSelectElement>("#promotionAccountSelect");
    const promotionStrategyInput = find<HTMLInputElement>("#promotionStrategyInput");

    promotionLoadBtn?.addEventListener("click", () => {
      void loadPromotionOverview();
    });
    promotionAccountSelect?.addEventListener("change", () => {
      void loadPromotionOverview();
    });
    promotionStrategyInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        void loadPromotionOverview();
      }
    });
  }

  return {
    loadPromotionOverview,
    wireActions,
  };
}
