import apiData from "../assets/api.json";
import commandsData from "../assets/commands.json";
import overviewData from "../assets/overview.json";
import { find } from "../lib/dom";
import { esc } from "../lib/format";
import type { AboutStat, OverviewFacts } from "../types/about";
import type { CatalogData } from "../types/catalog";

export interface AboutFeature {
  wireActions: () => void;
}

export interface AboutOptions {
  onOpenTab: (target: string) => void;
}

const STYLE_LABELS: Record<string, string> = {
  trend: "trend",
  mean_reversion: "mean-reversion",
};

function countKind(catalog: CatalogData, kind: string): number {
  return catalog.commands.filter((entry) => entry.kind === kind).length;
}

function strategyDetail(facts: OverviewFacts): string {
  return Object.entries(facts.strategies.by_style)
    .map(([style, count]) => `${count} ${STYLE_LABELS[style] ?? style}`)
    .join(", ");
}

export function buildStats(catalog: CatalogData, endpointCount: number, facts: OverviewFacts): AboutStat[] {
  return [
    {
      label: "CLI commands",
      value: String(countKind(catalog, "cli")),
      detail: "accounts, reporting, settings, backtesting, advisor",
      targetTab: "catalog",
    },
    {
      label: "Runtime jobs",
      value: String(countKind(catalog, "job")),
      detail: "daily, maintenance, and governance",
      targetTab: "catalog",
    },
    {
      label: "Scripts and checks",
      value: String(countKind(catalog, "tool")),
      detail: "quality gates, data operations, launchers",
      targetTab: "catalog",
    },
    { label: "API endpoints", value: String(endpointCount), detail: "FastAPI, local-only", targetTab: "docs" },
    {
      label: "Strategies",
      value: String(facts.strategies.total),
      detail: strategyDetail(facts),
      targetTab: "strategy-lab",
    },
    { label: "Database tables", value: String(facts.database_tables), detail: "SQLite, numbered migrations" },
    {
      label: "Python tests",
      value: `${facts.python_tests_floor.toLocaleString("en-US")}+`,
      detail: "unit, integration, and end-to-end",
    },
    { label: "Design decisions", value: String(facts.adrs), detail: "recorded as ADRs" },
  ];
}

export function renderStat(stat: AboutStat): string {
  const body = `
    <span class="about-stat-value">${esc(stat.value)}</span>
    <span class="about-stat-label">${esc(stat.label)}</span>
    <span class="about-stat-detail">${esc(stat.detail)}</span>
  `;
  return stat.targetTab
    ? `<button type="button" class="about-stat about-stat--link" data-about-open="${esc(stat.targetTab)}">${body}</button>`
    : `<div class="about-stat">${body}</div>`;
}

export function renderStats(stats: AboutStat[]): string {
  return stats.map(renderStat).join("");
}

export function createAboutFeature(
  options: AboutOptions,
  catalog: CatalogData = commandsData as CatalogData,
  facts: OverviewFacts = overviewData as OverviewFacts,
  endpointCount: number = apiData.endpoints.length,
): AboutFeature {
  function wireActions(): void {
    const stats = find<HTMLElement>("#aboutStats");
    if (stats) {
      stats.innerHTML = renderStats(buildStats(catalog, endpointCount, facts));
    }
    find<HTMLElement>("#tab-about")?.addEventListener("click", (event) => {
      const trigger = (event.target as HTMLElement).closest<HTMLElement>("[data-about-open]");
      if (trigger?.dataset.aboutOpen) {
        options.onOpenTab(trigger.dataset.aboutOpen);
      }
    });
  }

  return { wireActions };
}
