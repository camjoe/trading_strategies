import { find } from "../../lib/dom";
import { esc } from "../../lib/format";
import { getJson } from "../../lib/http";
import type { CsvExportBatch, CsvExportListResponse, CsvPreviewResponse } from "./types";


export interface AdminArtifactsController {
  loadCsvExports: () => Promise<void>;
  wireActions: () => void;
}


export function createAdminArtifactsController(): AdminArtifactsController {
  let cachedCsvExports: CsvExportBatch[] = [];

  function selectedCsvBatch(): CsvExportBatch | undefined {
    const exportSelect = find<HTMLSelectElement>("#csvExportSelect");
    if (!exportSelect?.value) return undefined;
    return cachedCsvExports.find((item) => item.name === exportSelect.value);
  }

  function renderCsvPreview(data: CsvPreviewResponse): void {
    const output = find<HTMLDivElement>("#csvPreviewOutput");
    const meta = find<HTMLDivElement>("#csvPreviewMeta");
    if (!output || !meta) return;

    const colCount = Math.max(
      data.header.length,
      ...data.rows.map((row) => row.length),
      1,
    );
    const headers = data.header.length
      ? data.header
      : Array.from({ length: colCount }, (_, idx) => `col_${idx + 1}`);

    const headHtml = headers
      .map((h) => `<th>${esc(h)}</th>`)
      .join("");
    const bodyHtml = data.rows
      .map((row) => {
        const cells = Array.from({ length: colCount }, (_, idx) => esc(row[idx] ?? ""));
        return `<tr>${cells.map((cell) => `<td>${cell}</td>`).join("")}</tr>`;
      })
      .join("");

    output.innerHTML = `
      <table class="compare-table admin-csv-table">
        <thead><tr>${headHtml}</tr></thead>
        <tbody>${bodyHtml || `<tr><td colspan="${colCount}">No rows available.</td></tr>`}</tbody>
      </table>
    `;

    meta.textContent = `${data.exportName} / ${data.fileName} - ${data.returned} row(s) shown${data.truncated ? " (truncated)" : ""}.`;
  }

  function syncCsvFileSelect(): void {
    const fileSelect = find<HTMLSelectElement>("#csvFileSelect");
    const output = find<HTMLDivElement>("#csvPreviewOutput");
    const meta = find<HTMLDivElement>("#csvPreviewMeta");
    if (!fileSelect) return;

    const batch = selectedCsvBatch();
    if (!batch) {
      fileSelect.innerHTML = `<option value="">Select CSV file</option>`;
      if (output) output.innerHTML = `<div class="empty">Choose an export and CSV file to preview.</div>`;
      if (meta) meta.textContent = "No CSV loaded yet.";
      return;
    }

    const optionsHtml = batch.files
      .map((f) => `<option value="${esc(f.name)}">${esc(f.name)}</option>`)
      .join("");
    fileSelect.innerHTML = `<option value="">Select CSV file</option>${optionsHtml}`;

    if (output) output.innerHTML = `<div class="empty">Select a CSV file and click Load Preview.</div>`;
    if (meta) meta.textContent = `${batch.name} selected. Pick a file to preview.`;
  }

  async function loadCsvExports(): Promise<void> {
    const exportSelect = find<HTMLSelectElement>("#csvExportSelect");
    const fileSelect = find<HTMLSelectElement>("#csvFileSelect");
    const output = find<HTMLDivElement>("#csvPreviewOutput");
    const meta = find<HTMLDivElement>("#csvPreviewMeta");
    if (!exportSelect || !fileSelect || !output || !meta) return;

    const data = await getJson<CsvExportListResponse>("/api/admin/exports/csv");
    cachedCsvExports = data.exports;

    if (!cachedCsvExports.length) {
      exportSelect.innerHTML = `<option value="">No export batches found</option>`;
      fileSelect.innerHTML = `<option value="">No CSV files found</option>`;
      output.innerHTML = `<div class="empty">No exports available in local/exports yet.</div>`;
      meta.textContent = "Run python scripts/data_ops/export_db_csv.py or python scripts/data_ops/export_db_csv_zip.py to generate db_csv_* database table snapshots first.";
      return;
    }

    const exportOptions = cachedCsvExports
      .map((item) => `<option value="${esc(item.name)}">${esc(item.name)}</option>`)
      .join("");
    exportSelect.innerHTML = `<option value="">Select export batch</option>${exportOptions}`;
    exportSelect.value = cachedCsvExports[0].name;
    syncCsvFileSelect();
  }

  async function loadCsvPreview(): Promise<void> {
    const exportSelect = find<HTMLSelectElement>("#csvExportSelect");
    const fileSelect = find<HTMLSelectElement>("#csvFileSelect");
    const meta = find<HTMLDivElement>("#csvPreviewMeta");
    if (!exportSelect || !fileSelect || !meta) return;

    const exportName = exportSelect.value;
    const fileName = fileSelect.value;
    if (!exportName || !fileName) {
      meta.textContent = "Select both export batch and CSV file first.";
      return;
    }

    meta.textContent = "Loading CSV preview...";
    const q = new URLSearchParams({
      exportName,
      fileName,
      limit: "250",
    });
    const data = await getJson<CsvPreviewResponse>(`/api/admin/exports/csv/preview?${q.toString()}`);
    renderCsvPreview(data);
  }

  function wireActions(): void {
    const exportSelect = find<HTMLSelectElement>("#csvExportSelect");
    const loadPreviewBtn = find<HTMLButtonElement>("#csvPreviewLoadBtn");
    const refreshBtn = find<HTMLButtonElement>("#csvRefreshBtn");

    exportSelect?.addEventListener("change", () => {
      syncCsvFileSelect();
    });
    loadPreviewBtn?.addEventListener("click", () => {
      void loadCsvPreview();
    });
    refreshBtn?.addEventListener("click", () => {
      void loadCsvExports();
    });
  }

  return {
    loadCsvExports,
    wireActions,
  };
}
