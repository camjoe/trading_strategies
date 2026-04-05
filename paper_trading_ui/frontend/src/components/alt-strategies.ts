import { esc } from "../lib/format";
import type { ProviderStatus, SignalOutput, SignalsResponse } from "../types";

// ---------------------------------------------------------------------------
// Provider status cards
// ---------------------------------------------------------------------------

function renderKeyScores(scores: Record<string, number>): string {
  const entries = Object.entries(scores);
  if (entries.length === 0) {
    return `<span class="empty">—</span>`;
  }
  const rows = entries
    .map(([k, v]) => `<tr><td>${esc(k)}</td><td>${v.toFixed(4)}</td></tr>`)
    .join("");
  return `<table><thead><tr><th>Feature</th><th>Value</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderProviderCard(provider: ProviderStatus): string {
  const badge = provider.available
    ? `<span class="up">✓ Available</span>`
    : `<span class="down">✗ Unavailable</span>`;
  const fetchedAt = new Date(provider.fetched_at).toLocaleString();

  return `
    <div class="alt-provider-card">
      <div class="alt-provider-card-head">
        <strong>${esc(provider.name)}</strong>
        <span class="chip">${esc(provider.source_label)}</span>
      </div>
      <div>${badge}</div>
      <p class="alt-provider-card-meta">Last fetched: ${esc(fetchedAt)}</p>
      ${renderKeyScores(provider.key_scores)}
    </div>
  `;
}

export function renderProviderCards(providers: ProviderStatus[]): string {
  if (providers.length === 0) {
    return `<div class="empty">No providers available.</div>`;
  }
  return providers.map(renderProviderCard).join("");
}

// ---------------------------------------------------------------------------
// Signal output table
// ---------------------------------------------------------------------------

function signalClass(signal: SignalOutput["signal"]): string {
  if (signal === "buy") return "up";
  if (signal === "sell") return "down";
  return "";
}

function renderFeaturesCell(features: Record<string, number>): string {
  const entries = Object.entries(features);
  if (entries.length === 0) return "—";
  return entries.map(([k, v]) => `${esc(k)}: ${v.toFixed(4)}`).join(", ");
}

function renderSignalRow(output: SignalOutput): string {
  const cls = signalClass(output.signal);
  const availableText = output.available ? "✓" : "✗";
  return `
    <tr>
      <td>${esc(output.strategy)}</td>
      <td class="${cls}">${esc(output.signal.toUpperCase())}</td>
      <td>${availableText}</td>
      <td>${renderFeaturesCell(output.features)}</td>
    </tr>
  `;
}

export function renderSignalRows(response: SignalsResponse): string {
  const rows = response.signals.map(renderSignalRow).join("");
  return `
    <table>
      <thead>
        <tr>
          <th>Strategy</th>
          <th>Signal</th>
          <th>Available</th>
          <th>Key Features</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}
