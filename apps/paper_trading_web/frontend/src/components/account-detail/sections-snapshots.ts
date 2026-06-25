import { currency, esc } from "../../lib/format";
import type { AccountDetail } from "../../types/accounts";
import type { DetailSectionName } from "./types";

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

export function renderSnapshotsSection(
  detail: AccountDetail,
  activeSection: DetailSectionName,
  snapRows: string,
): string {
  return `
    <article class="detail-section-panel" data-detail-panel="snapshots" ${activeSection === "snapshots" ? "" : "hidden"}>
      <h4>Equity Snapshots</h4>
      ${detail.liveBenchmarkOverlay ? renderBenchmarkOverlaySparkline(detail.liveBenchmarkOverlay) : ""}
      ${renderEquitySparkline(detail.snapshots, { title: "Live Equity Curve" })}
      <table>
        <thead><tr><th>Time</th><th>Equity</th><th>Cash</th><th>Market Value</th></tr></thead>
        <tbody>${snapRows || `<tr><td colspan="4">No snapshots yet.</td></tr>`}</tbody>
      </table>
    </article>
  `;
}
