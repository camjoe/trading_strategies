// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

import commandsData from "../../assets/commands.json";
import {
  DEFAULT_FILTER,
  createCatalogFeature,
  filterEntries,
  formatDefault,
  renderCatalog,
  renderEntry,
  renderFamily,
  renderSummary,
} from "../../features/catalog";
import catalogTemplate from "../../views/catalog.html?raw";
import type { CatalogData, CatalogEntry } from "../../types/catalog";

function makeEntry(overrides: Partial<CatalogEntry> = {}): CatalogEntry {
  return {
    name: "snapshot",
    kind: "cli",
    group: "Reporting",
    family: null,
    risk: "writes-local",
    module: null,
    schedule: null,
    runnable: false,
    help: "Save equity snapshot for an account.",
    example: "python -m app snapshot --account <ACCOUNT>",
    arguments: [
      {
        flags: ["--account"],
        dest: "account",
        scope: "command",
        positional: false,
        kind: "value",
        type: "str",
        required: true,
        default: null,
        choices: null,
        help: "Account name",
      },
      {
        flags: ["--time"],
        dest: "time",
        scope: "command",
        positional: false,
        kind: "value",
        type: "str",
        required: false,
        default: "now",
        choices: ["now", "close"],
        help: "Snapshot time",
      },
    ],
    ...overrides,
  };
}

function makeData(): CatalogData {
  return {
    schema_version: 2,
    cli_invocation: "python -m app",
    groups: [
      { name: "Reporting", kind: "cli" },
      { name: "Daily Jobs", kind: "job" },
    ],
    families: [],
    commands: [
      makeEntry(),
      makeEntry({ name: "report", risk: "read-only", help: "Show account status.", arguments: [] }),
      makeEntry({
        name: "daily-paper-trading",
        kind: "job",
        group: "Daily Jobs",
        risk: "broker",
        schedule: "weekdays",
        module: "jobs.daily",
        help: "Run the daily workflow.",
        arguments: [],
      }),
    ],
  };
}

describe("filterEntries", () => {
  it("returns everything for the default filter", () => {
    expect(filterEntries(makeData().commands, DEFAULT_FILTER)).toHaveLength(3);
  });

  it("matches every search term against name, help, module, and argument text", () => {
    const entries = makeData().commands;

    expect(filterEntries(entries, { ...DEFAULT_FILTER, query: "equity snapshot" }).map((e) => e.name)).toEqual([
      "snapshot",
    ]);
    expect(filterEntries(entries, { ...DEFAULT_FILTER, query: "--time" }).map((e) => e.name)).toEqual(["snapshot"]);
    expect(filterEntries(entries, { ...DEFAULT_FILTER, query: "jobs.daily" }).map((e) => e.name)).toEqual([
      "daily-paper-trading",
    ]);
    expect(filterEntries(entries, { ...DEFAULT_FILTER, query: "snapshot nonsense" })).toEqual([]);
  });

  it("combines kind and risk filters with the search", () => {
    const entries = makeData().commands;

    expect(filterEntries(entries, { ...DEFAULT_FILTER, kind: "job" }).map((e) => e.name)).toEqual([
      "daily-paper-trading",
    ]);
    expect(filterEntries(entries, { ...DEFAULT_FILTER, risk: "read-only" }).map((e) => e.name)).toEqual(["report"]);
    expect(filterEntries(entries, { query: "report", kind: "job", risk: "all" })).toEqual([]);
  });
});

describe("formatDefault", () => {
  it("hides empty defaults and joins lists", () => {
    expect(formatDefault(null)).toBe("");
    expect(formatDefault(false)).toBe("");
    expect(formatDefault("")).toBe("");
    expect(formatDefault(20)).toBe("20");
    expect(formatDefault(["a", "b"])).toBe("a, b");
  });
});

describe("renderEntry", () => {
  it("shows the risk label, schedule, example, and argument details", () => {
    const html = renderEntry(makeEntry({ schedule: "weekdays" }));

    expect(html).toContain("Writes local data");
    expect(html).toContain("weekdays");
    expect(html).toContain("python -m app snapshot --account &lt;ACCOUNT&gt;");
    expect(html).toContain("required");
    expect(html).toContain("Choices: now, close");
    expect(html).toContain('data-catalog-copy="python -m app snapshot --account &lt;ACCOUNT&gt;"');
  });

  it("states when an entry takes no arguments", () => {
    expect(renderEntry(makeEntry({ arguments: [] }))).toContain("Takes no arguments.");
  });

  it("escapes markup in names and help text", () => {
    const html = renderEntry(makeEntry({ name: "<b>x</b>", help: "<script>alert(1)</script>" }));

    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;b&gt;x&lt;/b&gt;");
  });
});

describe("renderCatalog", () => {
  it("groups entries by kind and group with counts", () => {
    const html = renderCatalog(makeData(), DEFAULT_FILTER);

    expect(html).toContain("CLI commands");
    expect(html).toContain("Runtime jobs");
    expect(html).not.toContain("Scripts and tools");
    expect(html).toContain("Reporting");
    expect(html).toContain("Daily Jobs");
  });

  it("shows an empty state when nothing matches", () => {
    expect(renderCatalog(makeData(), { ...DEFAULT_FILTER, query: "zzz" })).toContain("No commands match");
  });
});

describe("families", () => {
  function familyData(): CatalogData {
    const data = makeData();
    return {
      ...data,
      groups: [...data.groups, { name: "Quality Checks", kind: "tool" }],
      families: [{ name: "run-checks", help: "Run a bundle of checks." }],
      commands: [
        ...data.commands,
        makeEntry({ name: "run-checks docs", kind: "tool", group: "Quality Checks", family: "run-checks" }),
        makeEntry({ name: "fix-checks", kind: "tool", group: "Quality Checks", help: "Apply fixes." }),
        makeEntry({ name: "run-checks repo", kind: "tool", group: "Quality Checks", family: "run-checks" }),
      ],
    };
  }

  it("renders a family as one row at its first member, before the entries that follow it", () => {
    const html = renderCatalog(familyData(), { ...DEFAULT_FILTER, kind: "tool" });

    expect(html.match(/data-catalog-family=/g)).toHaveLength(1);
    expect(html.indexOf('data-catalog-family="run-checks"')).toBeLessThan(html.indexOf('data-catalog-entry="fix-checks"'));
    expect(html).toContain('data-catalog-entry="run-checks repo"');
  });

  it("lists members without the family prefix and shows each risk once", () => {
    const html = renderFamily({ name: "run-checks", help: "Run a bundle." }, [
      makeEntry({ name: "run-checks docs", risk: "read-only" }),
      makeEntry({ name: "run-checks repo", risk: "read-only" }),
    ]);

    const summary = html.split("</summary>")[0];
    expect(summary).toContain("<code>docs</code><code>repo</code>");
    expect(summary.match(/Read-only<\/span>/g)).toHaveLength(1);
    expect(html).not.toContain(" open");
  });

  it("opens families while a search is active", () => {
    const html = renderCatalog(familyData(), { ...DEFAULT_FILTER, query: "run-checks" });

    expect(html).toContain('data-catalog-family="run-checks" open');
  });
});

describe("renderSummary", () => {
  it("reports totals, then filtered counts", () => {
    const data = makeData();

    expect(renderSummary(data, 3)).toBe("3 entries: 2 CLI commands · 1 runtime jobs · 0 scripts and tools");
    expect(renderSummary(data, 1)).toBe("Showing 1 of 3 entries");
  });
});

describe("generated commands asset", () => {
  it("renders every entry and keeps names unique", () => {
    const data = commandsData as CatalogData;
    const names = data.commands.map((entry) => entry.name);

    expect(new Set(names).size).toBe(names.length);
    expect(renderCatalog(data, DEFAULT_FILTER).match(/class="catalog-entry"/g)).toHaveLength(names.length);
  });
});

describe("createCatalogFeature", () => {
  beforeEach(() => {
    document.body.innerHTML = catalogTemplate;
    createCatalogFeature(makeData()).wireActions();
  });

  it("renders the catalog and summary on wire-up", () => {
    expect(document.querySelectorAll(".catalog-entry")).toHaveLength(3);
    expect(document.getElementById("catalogSummary")?.textContent).toContain("3 entries");
  });

  it("filters while the user types", () => {
    const input = document.getElementById("catalogSearch") as HTMLInputElement;
    input.value = "daily";
    input.dispatchEvent(new Event("input", { bubbles: true }));

    expect(document.querySelectorAll(".catalog-entry")).toHaveLength(1);
    expect(document.getElementById("catalogSummary")?.textContent).toBe("Showing 1 of 3 entries");
  });

  it("filters by kind and risk and marks the active chip", () => {
    (document.querySelector('[data-catalog-kind="job"]') as HTMLButtonElement).click();
    expect(document.querySelectorAll(".catalog-entry")).toHaveLength(1);
    expect(document.querySelector('[data-catalog-kind="job"]')?.classList.contains("active")).toBe(true);
    expect(document.querySelector('[data-catalog-kind="all"]')?.classList.contains("active")).toBe(false);

    (document.querySelector('[data-catalog-kind="all"]') as HTMLButtonElement).click();
    (document.querySelector('[data-catalog-risk="read-only"]') as HTMLButtonElement).click();
    expect(document.querySelectorAll(".catalog-entry")).toHaveLength(1);
  });

  it("expands and collapses every entry", () => {
    (document.getElementById("catalogExpandAll") as HTMLButtonElement).click();
    expect(document.querySelectorAll<HTMLDetailsElement>(".catalog-entry[open]")).toHaveLength(3);

    (document.getElementById("catalogCollapseAll") as HTMLButtonElement).click();
    expect(document.querySelectorAll<HTMLDetailsElement>(".catalog-entry[open]")).toHaveLength(0);
  });

  it("copies the example to the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });

    const button = document.querySelector<HTMLButtonElement>("[data-catalog-copy]");
    button?.click();
    await vi.waitFor(() => expect(button?.textContent).toBe("Copied"));

    expect(writeText).toHaveBeenCalledWith("python -m app snapshot --account <ACCOUNT>");
  });
});
