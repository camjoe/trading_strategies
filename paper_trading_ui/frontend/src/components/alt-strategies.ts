import { esc } from "../lib/format";
import type { FeatureDescription, ProviderStatus, SignalOutput, SignalsResponse } from "../types";

// ---------------------------------------------------------------------------
// Provider status cards
// ---------------------------------------------------------------------------

function renderFeatureRow(name: string, value: number, meta?: FeatureDescription): string {
  const label = meta?.label ?? name;
  const desc = meta?.description ?? "";
  const formatted = Number.isInteger(value) ? String(value) : value.toFixed(4);
  return `
    <tr>
      <td class="feature-name" title="${esc(desc)}">${esc(label)}</td>
      <td class="feature-value">${esc(formatted)}</td>
      <td class="feature-desc">${esc(desc)}</td>
    </tr>`;
}

function renderKeyScores(
  scores: Record<string, number>,
  featureDescriptions?: Record<string, FeatureDescription>,
): string {
  const entries = Object.entries(scores);
  if (entries.length === 0) {
    return `<span class="empty">—</span>`;
  }
  const rows = entries
    .map(([k, v]) => renderFeatureRow(k, v, featureDescriptions?.[k]))
    .join("");
  return `<table class="feature-table">
    <thead><tr><th>Feature</th><th>Value</th><th>What it means</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function renderDataSources(sources?: string[]): string {
  if (!sources || sources.length === 0) return "";
  const tags = sources.map((s) => `<span class="data-source-tag">${esc(s)}</span>`).join(" ");
  return `<div class="data-sources"><strong>Sources:</strong> ${tags}</div>`;
}

function renderProviderCard(provider: ProviderStatus): string {
  const badge = provider.available
    ? `<span class="up">✓ Available</span>`
    : `<span class="down">✗ Unavailable</span>`;
  const fetchedAt = new Date(provider.fetched_at).toLocaleString();

  const description = provider.description
    ? `<p class="alt-provider-description">${esc(provider.description)}</p>`
    : "";

  const signalLogic = provider.signal_logic
    ? `<details class="signal-logic-details">
        <summary>Signal Logic</summary>
        <p>${esc(provider.signal_logic)}</p>
      </details>`
    : "";

  return `
    <div class="alt-provider-card">
      <div class="alt-provider-card-head">
        <strong>${esc(provider.name)}</strong>
        <span class="chip">${esc(provider.source_label)}</span>
        ${badge}
      </div>
      ${description}
      ${renderDataSources(provider.data_sources)}
      <p class="alt-provider-card-meta">Last fetched: ${esc(fetchedAt)}</p>
      ${
        Object.keys(provider.key_scores).length > 0
          ? `<details class="signal-logic-details">
              <summary class="muted">Sample scores (health probe — SPY)</summary>
              ${renderKeyScores(provider.key_scores, provider.feature_descriptions)}
            </details>`
          : ""
      }
      ${signalLogic}
    </div>
  `;
}

export function renderProviderCards(providers: ProviderStatus[]): string {
  if (providers.length === 0) {
    return `<div class="empty">No providers available.</div>`;
  }
  const note = `<p class="muted provider-health-note">Provider health is checked automatically using SPY as a reference ticker. Enter a ticker below to get strategy signals for a specific stock.</p>`;
  return note + `<div class="alt-providers-cards">${providers.map(renderProviderCard).join("")}</div>`;
}

// ---------------------------------------------------------------------------
// Signal output table
// ---------------------------------------------------------------------------

function signalClass(signal: SignalOutput["signal"]): string {
  if (signal === "buy") return "up";
  if (signal === "sell") return "down";
  return "";
}

function renderFeatureBreakdown(
  features: Record<string, number>,
  descriptions?: Record<string, FeatureDescription>,
): string {
  const rows = Object.entries(features)
    .map(([k, v]) => {
      const desc = descriptions?.[k];
      const label = desc?.label ?? k;
      const hint = desc?.description ?? "";
      const formatted = Number.isInteger(v) ? String(v) : v.toFixed(4);
      return `<tr>
        <td class="feature-name">${esc(label)}</td>
        <td class="feature-value">${esc(formatted)}</td>
        <td class="feature-desc muted">${esc(hint)}</td>
      </tr>`;
    })
    .join("");

  return `
    <details class="signal-feature-details">
      <summary>Feature breakdown</summary>
      <table class="feature-table">
        <thead><tr><th>Feature</th><th>Value</th><th>Threshold / Meaning</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </details>
  `;
}

function renderSignalRow(output: SignalOutput): string {
  const cls = signalClass(output.signal);
  const hasFeatures = Object.keys(output.features ?? {}).length > 0;

  const interpretation =
    output.interpretation ||
    (hasFeatures ? "—" : "Provider unavailable or no data returned for this ticker.");

  const featureDetails = hasFeatures
    ? renderFeatureBreakdown(output.features, output.feature_descriptions)
    : "";

  return `
    <tr>
      <td>${esc(output.strategy)}</td>
      <td class="${cls}">${esc(output.signal.toUpperCase())}</td>
      <td>
        <span>${esc(interpretation)}</span>
        ${featureDetails}
      </td>
    </tr>
  `;
}

export function renderSignalRows(response: SignalsResponse): string {
  const rows = response.signals.map(renderSignalRow).join("");
  return `
    <p class="muted signals-ticker-note">Signals for <strong>${esc(response.ticker)}</strong>. Feature-only analysis — momentum confirmation requires live price history, so these signals reflect data context only.</p>
    <table>
      <thead>
        <tr>
          <th>Strategy</th>
          <th>Signal</th>
          <th>Interpretation &amp; Data</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}
