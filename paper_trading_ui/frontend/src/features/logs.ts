import { find } from "../lib/dom";
import { esc } from "../lib/format";
import { getJson } from "../lib/http";
import { renderLogLines } from "../lib/logs";

export interface LogsFeature {
  loadLogFiles: () => Promise<void>;
  loadSelectedLog: () => Promise<void>;
  wireActions: () => void;
}

export function createLogsFeature(): LogsFeature {
  async function loadLogFiles(): Promise<void> {
    const select = find<HTMLSelectElement>("#logFileSelect");
    if (!select) return;

    const data = await getJson<{ files: string[] }>("/api/logs/files");
    if (!data.files.length) {
      select.innerHTML = `<option value="">No log files</option>`;
      return;
    }

    select.innerHTML = data.files.map((f) => `<option value="${esc(f)}">${esc(f)}</option>`).join("");
  }

  async function loadSelectedLog(): Promise<void> {
    const select = find<HTMLSelectElement>("#logFileSelect");
    const filterInput = find<HTMLInputElement>("#logFilterInput");
    const output = find<HTMLElement>("#logOutput");
    if (!select || !output || !filterInput) return;

    const file = select.value;
    if (!file) {
      output.textContent = "No log file selected.";
      return;
    }

    const contains = filterInput.value.trim();
    const query = new URLSearchParams({ limit: "400" });
    if (contains) {
      query.set("contains", contains);
    }

    const data = await getJson<{ lines: string[] }>(`/api/logs/${encodeURIComponent(file)}?${query.toString()}`);
    output.innerHTML = renderLogLines(data.lines);
  }

  function wireActions(): void {
    const loadLogBtn = find<HTMLButtonElement>("#loadLogBtn");
    loadLogBtn?.addEventListener("click", () => {
      void loadSelectedLog();
    });
  }

  return {
    loadLogFiles,
    loadSelectedLog,
    wireActions,
  };
}
