import { find } from "../lib/dom";
import { esc } from "../lib/format";
import { errorMessage, getJson, patchJson, postJson } from "../lib/http";
import type { AccountListItem } from "../types/accounts";

type Strategy = { id: number; strategyKey: string; primitive: string; params: Record<string, unknown>; description: string | null; status: string; enabled: boolean };
type Primitive = { primitive: string; style: string; description: string; default_params: Record<string, unknown> };
type Experiment = { id: number; accountName: string; primitive: string; winnerParams: Record<string, unknown>; windowCount: number; oosMeanWinnerReturnPct: number | null; oosMeanBaselineReturnPct: number | null; oosWindowsBeatBaseline: number | null; holdoutWinnerReturnPct: number | null; holdoutBaselineReturnPct: number | null; promotedStrategyId: number | null; createdAt: string };

function parseObject(raw: FormDataEntryValue | null, label: string): Record<string, unknown> {
  const parsed: unknown = JSON.parse(String(raw ?? "{}"));
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error(`${label} must be a JSON object.`);
  return parsed as Record<string, unknown>;
}

export function createStrategyLabFeature() {
  let strategies: Strategy[] = [];
  let primitives: Primitive[] = [];

  async function load(): Promise<void> {
    const [catalog, history, accounts] = await Promise.all([
      getJson<{ strategies: Strategy[]; primitives: Primitive[] }>("/api/strategy-lab/catalog"),
      getJson<{ experiments: Experiment[] }>("/api/strategy-lab/optimizations"),
      getJson<{ accounts: AccountListItem[] }>("/api/accounts"),
    ]);
    strategies = catalog.strategies;
    primitives = catalog.primitives;
    const primitiveSelect = find<HTMLSelectElement>("#strategyPrimitiveSelect");
    if (primitiveSelect) primitiveSelect.innerHTML = primitives.map(item => `<option value="${esc(item.primitive)}">${esc(item.primitive)} · ${esc(item.style)}</option>`).join("");
    const strategySelect = find<HTMLSelectElement>("#optimizationStrategySelect");
    if (strategySelect) strategySelect.innerHTML = strategies.filter(item => item.enabled).map(item => `<option value="${esc(item.strategyKey)}">${esc(item.strategyKey)}</option>`).join("");
    const accountSelect = find<HTMLSelectElement>("#optimizationAccountSelect");
    if (accountSelect) accountSelect.innerHTML = accounts.accounts.map(item => `<option value="${esc(item.name)}">${esc(item.displayName)}</option>`).join("");
    renderCatalog();
    renderExperiments(history.experiments);
  }

  function renderCatalog(): void {
    const output = find<HTMLElement>("#strategyCatalogOutput");
    if (!output) return;
    output.innerHTML = strategies.map(item => `<section class="config-summary-card">
      <div class="ops-card-head"><strong>${esc(item.strategyKey)}</strong><span class="status-pill ${item.enabled ? "ok" : "missing"}">${esc(item.status)} · ${item.enabled ? "enabled" : "disabled"}</span></div>
      <p class="admin-note">${esc(item.primitive)} · ${esc(item.description ?? "No description")}</p>
      <label class="bt-field"><span>Knob overrides</span><textarea class="strategy-params" data-strategy="${esc(item.strategyKey)}" rows="3"${item.status !== "draft" ? " disabled" : ""}>${esc(JSON.stringify(item.params, null, 2))}</textarea></label>
      <div class="edit-params-actions">
        <button class="strategy-save" data-strategy="${esc(item.strategyKey)}" type="button"${item.status !== "draft" ? " disabled" : ""}>Save knobs</button>
        <button class="strategy-toggle" data-strategy="${esc(item.strategyKey)}" data-enabled="${String(item.enabled)}" type="button">${item.enabled ? "Disable" : "Enable"}</button>
        <button class="strategy-freeze" data-strategy="${esc(item.strategyKey)}" type="button"${item.status !== "draft" ? " disabled" : ""}>Freeze</button>
      </div></section>`).join("");
    wireCatalogActions();
  }

  function renderExperiments(experiments: Experiment[]): void {
    const output = find<HTMLElement>("#optimizationHistoryOutput");
    if (!output) return;
    output.innerHTML = experiments.length ? experiments.map(item => `<section class="config-summary-card">
      <div class="ops-card-head"><strong>Experiment #${item.id}</strong><span class="status-pill ${item.promotedStrategyId ? "ok" : "warning"}">${item.promotedStrategyId ? "promoted" : "review"}</span></div>
      <p>${esc(item.accountName)} · ${esc(item.primitive)} · ${item.windowCount} windows</p>
      <pre>${esc(JSON.stringify(item.winnerParams, null, 2))}</pre>
      <p class="admin-note">OOS winner/default: ${item.oosMeanWinnerReturnPct ?? "n/a"} / ${item.oosMeanBaselineReturnPct ?? "n/a"} · holdout: ${item.holdoutWinnerReturnPct ?? "n/a"} / ${item.holdoutBaselineReturnPct ?? "n/a"}</p>
      ${item.promotedStrategyId ? "" : `<div class="bt-row"><input class="promotion-key" data-experiment="${item.id}" placeholder="new_strategy_key" /><button class="optimization-promote" data-experiment="${item.id}" type="button">Promote & freeze</button></div>`}
    </section>`).join("") : '<div class="empty">No optimization experiments yet.</div>';
    for (const button of Array.from(document.querySelectorAll<HTMLButtonElement>(".optimization-promote"))) button.addEventListener("click", async () => {
      const id = Number(button.dataset.experiment);
      const key = find<HTMLInputElement>(`.promotion-key[data-experiment="${id}"]`)?.value.trim();
      if (!key) return;
      if (!window.confirm(`Promote experiment #${id} as frozen strategy '${key}'?`)) return;
      await postJson(`/api/strategy-lab/optimizations/${id}/promote`, { strategyKey: key, freeze: true });
      await load();
    });
  }

  function wireCatalogActions(): void {
    for (const button of Array.from(document.querySelectorAll<HTMLButtonElement>(".strategy-save"))) button.addEventListener("click", async () => {
      const key = button.dataset.strategy ?? "";
      const raw = find<HTMLTextAreaElement>(`.strategy-params[data-strategy="${key}"]`)?.value ?? "{}";
      await patchJson(`/api/strategy-lab/catalog/${encodeURIComponent(key)}`, { params: parseObject(raw, "Knobs") });
      await load();
    });
    for (const button of Array.from(document.querySelectorAll<HTMLButtonElement>(".strategy-toggle"))) button.addEventListener("click", async () => {
      const key = button.dataset.strategy ?? "";
      await patchJson(`/api/strategy-lab/catalog/${encodeURIComponent(key)}`, { enabled: button.dataset.enabled !== "true" });
      await load();
    });
    for (const button of Array.from(document.querySelectorAll<HTMLButtonElement>(".strategy-freeze"))) button.addEventListener("click", async () => {
      if (!window.confirm("Freeze this strategy? Future tuning will require a new variant.")) return;
      await postJson(`/api/strategy-lab/catalog/${encodeURIComponent(button.dataset.strategy ?? "")}/freeze`);
      await load();
    });
  }

  function wireActions(): void {
    find<HTMLButtonElement>("#strategyLabRefreshBtn")?.addEventListener("click", () => void load());
    const createForm = find<HTMLFormElement>("#createStrategyForm");
    createForm?.addEventListener("submit", async event => {
      event.preventDefault();
      const data = new FormData(createForm);
      const message = find<HTMLElement>("#createStrategyMessage");
      try {
        await postJson("/api/strategy-lab/catalog", { strategyKey: data.get("strategyKey"), primitive: data.get("primitive"), params: parseObject(data.get("params"), "Knobs"), description: data.get("description") || null });
        if (message) message.textContent = "Draft created.";
        await load();
      } catch (error) { if (message) message.textContent = errorMessage(error, "Create failed."); }
    });
    const optimizationForm = find<HTMLFormElement>("#runOptimizationForm");
    optimizationForm?.addEventListener("submit", async event => {
      event.preventDefault();
      const data = new FormData(optimizationForm);
      const message = find<HTMLElement>("#optimizationMessage");
      try {
        const searchSpace = parseObject(data.get("searchSpace"), "Search space");
        const candidates = Object.values(searchSpace).reduce<number>(
          (count, values) => count * (Array.isArray(values) ? values.length : 0),
          1,
        );
        const budget = Number(data.get("candidateBudget"));
        if (!window.confirm(`Run a ${candidates}-candidate optimization (budget ${budget})? This may take several minutes.`)) return;
        if (message) message.textContent = "Optimization running…";
        const result = await postJson<{ experimentId: number }>("/api/strategy-lab/optimizations", { account: data.get("account"), strategy: data.get("strategy"), searchSpace, lookbackMonths: Number(data.get("lookbackMonths")), candidateBudget: budget, holdoutMonths: Number(data.get("holdoutMonths")) });
        if (message) message.textContent = `Experiment #${result.experimentId} completed.`;
        await load();
      } catch (error) { if (message) message.textContent = errorMessage(error, "Optimization failed."); }
    });
  }
  return { load, wireActions };
}
