import { renderOperationsOverview } from "../../components/admin-ops";
import { find } from "../../lib/dom";
import { errorMessage, getJson } from "../../lib/http";
import type { OperationsOverviewResponse } from "../../types";
import { setHtml, setOutput } from "./ui";


export interface AdminOperationsController {
  loadOperationsOverview: () => Promise<void>;
  wireActions: () => void;
}


export function createAdminOperationsController(): AdminOperationsController {
  async function loadOperationsOverview(): Promise<void> {
    const output = find<HTMLDivElement>("#adminOpsOutput");
    const meta = find<HTMLDivElement>("#adminOpsMeta");
    if (!output || !meta) return;

    meta.textContent = "Loading runtime status...";
    try {
      const data = await getJson<OperationsOverviewResponse>("/api/admin/operations/overview");
      setHtml(output, "admin-ops-output", renderOperationsOverview(data));
      meta.textContent =
        `${data.jobs.length} jobs tracked · ` +
        `${data.dailyBacktestRefreshArtifacts.length} refresh artifacts · ` +
        `${data.dailySnapshotArtifacts.length} snapshot artifacts · ` +
        `${data.databaseBackups.length} DB backups.`;
    } catch (error) {
      setOutput(output, "error", errorMessage(error, "Failed to load operations overview."));
      meta.textContent = "Operations overview unavailable.";
    }
  }

  function wireActions(): void {
    const refreshBtn = find<HTMLButtonElement>("#adminOpsRefreshBtn");
    refreshBtn?.addEventListener("click", () => {
      void loadOperationsOverview();
    });
  }

  return {
    loadOperationsOverview,
    wireActions,
  };
}
