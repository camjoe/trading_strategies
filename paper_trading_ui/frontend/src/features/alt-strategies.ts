import { find } from "../lib/dom";
import { esc } from "../lib/format";
import { getJson, postJson } from "../lib/http";
import { renderProviderCards, renderSignalRows } from "../components/alt-strategies";
import type { ProviderStatus, ProviderStatusResponse, SignalsResponse } from "../types";

const STATUS_PATH = "/api/features/status" as const;
const SIGNALS_PATH = "/api/features/signals" as const;

type HealthState = "up" | "partial" | "down";

export interface AltStrategiesFeature {
  loadStatus: () => Promise<void>;
  fetchProviderHealth: () => Promise<void>;
  wireActions: () => void;
}

function computeHealthState(providers: ProviderStatus[]): HealthState {
  if (!providers.length) return "down";
  const available = providers.filter((p) => p.available).length;
  if (available === providers.length) return "up";
  if (available === 0) return "down";
  return "partial";
}

function updateHealthBadge(health: HealthState): void {
  const tabBtn = find<HTMLButtonElement>('[data-tab="alt-strategies"]');
  if (!tabBtn) return;

  let dot = tabBtn.querySelector<HTMLSpanElement>(".tab-health-dot");
  if (!dot) {
    dot = document.createElement("span");
    dot.className = "tab-health-dot";
    tabBtn.appendChild(dot);
  }

  dot.classList.remove("tab-health-dot--up", "tab-health-dot--partial", "tab-health-dot--down");
  dot.classList.add(`tab-health-dot--${health}`);
}

export function createAltStrategiesFeature(): AltStrategiesFeature {
  async function loadStatus(): Promise<void> {
    const grid = find<HTMLDivElement>("#alt-providers-grid");
    if (!grid) return;

    grid.innerHTML = `<div class="empty">Loading…</div>`;
    try {
      const data = await getJson<ProviderStatusResponse>(STATUS_PATH);
      grid.innerHTML = renderProviderCards(data.providers);
      updateHealthBadge(computeHealthState(data.providers));
    } catch (err) {
      grid.innerHTML = `<div class="error">${esc(err instanceof Error ? err.message : "Failed to load provider status.")}</div>`;
    }
  }

  async function fetchProviderHealth(): Promise<void> {
    try {
      const data = await getJson<ProviderStatusResponse>(STATUS_PATH);
      updateHealthBadge(computeHealthState(data.providers));
    } catch {
      // Badge stays hidden on failure — silently ignore
    }
  }

  async function onSignalsSubmit(event: Event): Promise<void> {
    event.preventDefault();
    const form = event.currentTarget as HTMLFormElement;
    const resultEl = find<HTMLDivElement>("#alt-signals-result");

    const data = new FormData(form);
    const ticker = ((data.get("ticker") as string | null) ?? "").trim().toUpperCase();

    if (!ticker) {
      if (resultEl) {
        resultEl.className = "error";
        resultEl.textContent = "Please enter a ticker symbol.";
      }
      return;
    }

    if (resultEl) {
      resultEl.className = "";
      resultEl.innerHTML = `<div class="empty">Loading…</div>`;
    }

    try {
      const response = await postJson<SignalsResponse>(SIGNALS_PATH, { ticker });
      if (resultEl) {
        resultEl.className = "";
        resultEl.innerHTML = renderSignalRows(response);
      }
    } catch (err) {
      if (resultEl) {
        resultEl.className = "error";
        resultEl.textContent = err instanceof Error ? err.message : "Failed to load signals.";
      }
    }
  }

  function wireActions(): void {
    find<HTMLButtonElement>("#alt-refresh-btn")?.addEventListener("click", () => {
      void loadStatus();
    });

    find<HTMLFormElement>("#alt-signals-form")?.addEventListener("submit", (event) => {
      void onSignalsSubmit(event);
    });

    // Lazy-load whenever the tab is opened for the first time.
    const tabBtn = find<HTMLButtonElement>('[data-tab="alt-strategies"]');
    tabBtn?.addEventListener("click", () => {
      void loadStatus();
    });
  }

  return { loadStatus, fetchProviderHealth, wireActions };
}
