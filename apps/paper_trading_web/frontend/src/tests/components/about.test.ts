// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

import commandsData from "../../assets/commands.json";
import overviewData from "../../assets/overview.json";
import { buildStats, createAboutFeature, renderStat } from "../../features/about";
import aboutTemplate from "../../views/about.html?raw";
import navTemplate from "../../views/nav.html?raw";
import type { OverviewFacts } from "../../types/about";
import type { CatalogData } from "../../types/catalog";

const catalog = {
  schema_version: 2,
  cli_invocation: "python -m app",
  groups: [],
  commands: [
    { name: "a", kind: "cli" },
    { name: "b", kind: "cli" },
    { name: "c", kind: "job" },
    { name: "d", kind: "tool" },
  ],
} as unknown as CatalogData;

const facts: OverviewFacts = {
  schema_version: 1,
  database_tables: 28,
  strategies: { total: 8, by_style: { mean_reversion: 3, trend: 5 } },
  adrs: 14,
  python_tests_floor: 2500,
};

describe("buildStats", () => {
  it("counts entries by kind and reads the generated facts", () => {
    const stats = Object.fromEntries(buildStats(catalog, 36, facts).map((stat) => [stat.label, stat]));

    expect(stats["CLI commands"].value).toBe("2");
    expect(stats["Runtime jobs"].value).toBe("1");
    expect(stats["Scripts and checks"].value).toBe("1");
    expect(stats["API endpoints"].value).toBe("36");
    expect(stats["Strategies"].detail).toBe("3 mean-reversion, 5 trend");
    expect(stats["Database tables"].value).toBe("28");
    expect(stats["Python tests"].value).toBe("2,500+");
    expect(stats["Design decisions"].value).toBe("14");
  });

  it("builds from the generated assets without a missing value", () => {
    const stats = buildStats(commandsData as CatalogData, 1, overviewData as OverviewFacts);

    for (const stat of stats) {
      expect(stat.value).not.toBe("0");
      expect(stat.value).not.toBe("NaN");
    }
  });
});

describe("renderStat", () => {
  it("renders a link button only when the stat has a target tab", () => {
    expect(renderStat({ label: "A", value: "1", detail: "d", targetTab: "catalog" })).toContain(
      'data-about-open="catalog"',
    );
    expect(renderStat({ label: "A", value: "1", detail: "d" })).not.toContain("data-about-open");
  });

  it("escapes markup", () => {
    expect(renderStat({ label: "<i>", value: "1", detail: "d" })).toContain("&lt;i&gt;");
  });
});

describe("createAboutFeature", () => {
  const onOpenTab = vi.fn();

  beforeEach(() => {
    onOpenTab.mockClear();
    document.body.innerHTML = aboutTemplate;
    createAboutFeature({ onOpenTab }, catalog, facts, 36).wireActions();
  });

  it("renders every stat tile", () => {
    expect(document.querySelectorAll("#aboutStats .about-stat")).toHaveLength(8);
  });

  it("opens the tab named by a stat, a step, or an action button", () => {
    document.querySelector<HTMLElement>('#aboutStats [data-about-open="catalog"]')?.click();
    document.querySelector<HTMLElement>('.about-step[data-about-open="backtesting"]')?.click();
    document.querySelector<HTMLElement>('.about-actions [data-about-open="accounts"]')?.click();

    expect(onOpenTab.mock.calls.map((call) => call[0])).toEqual(["catalog", "backtesting", "accounts"]);
  });

  it("links only to tabs that exist in the navigation", () => {
    const targets = Array.from(document.querySelectorAll<HTMLElement>("[data-about-open]")).map(
      (element) => element.dataset.aboutOpen ?? "",
    );
    document.body.insertAdjacentHTML("beforeend", navTemplate);

    expect(targets.length).toBeGreaterThan(8);
    for (const target of new Set(targets)) {
      expect(document.querySelector(`.tab-btn[data-tab="${target}"]`), target).not.toBeNull();
    }
  });

  it("describes the diagram for assistive technology", () => {
    expect(document.querySelector("svg[role='img'] title")?.textContent).toBe("Architecture layers");
    expect(document.querySelector("svg[role='img'] desc")?.textContent).toContain("Interfaces call services");
  });
});
