// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

import commandsData from "../../assets/commands.json";
import {
  buildCatalogTemplate,
  createCatalogFeature,
  filterEntries,
  formatDefault,
  renderCatalog,
  renderEntry,
  renderFamily,
  renderSummary,
} from "../../features/catalog";
import type { CatalogData, CatalogEntry, CatalogFilter } from "../../types/catalog";

const CLI: CatalogFilter = { query: "", kind: "cli" };

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
  it("returns every entry of the kind when the search is empty", () => {
    expect(filterEntries(makeData().commands, CLI).map((e) => e.name)).toEqual(["snapshot", "report"]);
  });

  it("matches every search term against name, help, module, and argument text", () => {
    const entries = makeData().commands;

    expect(filterEntries(entries, { ...CLI, query: "equity snapshot" }).map((e) => e.name)).toEqual(["snapshot"]);
    expect(filterEntries(entries, { ...CLI, query: "--time" }).map((e) => e.name)).toEqual(["snapshot"]);
    expect(filterEntries(entries, { kind: "job", query: "jobs.daily" }).map((e) => e.name)).toEqual([
      "daily-paper-trading",
    ]);
    expect(filterEntries(entries, { ...CLI, query: "snapshot nonsense" })).toEqual([]);
  });

  it("searches only the entries of its own kind", () => {
    expect(filterEntries(makeData().commands, { query: "report", kind: "job" })).toEqual([]);
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
  it("renders only the groups of its kind", () => {
    const html = renderCatalog(makeData(), CLI);

    expect(html).toContain("Reporting");
    expect(html).not.toContain("Daily Jobs");
  });

  it("shows an empty state when nothing matches", () => {
    expect(renderCatalog(makeData(), { ...CLI, query: "zzz" })).toContain("No commands match");
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
    const html = renderCatalog(familyData(), { query: "", kind: "tool" });

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

  it("shows the schedule of its first member", () => {
    const html = renderFamily({ name: "Daily", help: "Pipeline." }, [
      makeEntry({ name: "daily", schedule: "weekdays" }),
      makeEntry({ name: "step", schedule: "indirect" }),
    ]);
    const summary = html.split("</summary>")[0];

    expect(summary).toContain('<span class="chip">weekdays</span>');
    expect(summary).not.toContain("indirect");
  });

  it("opens families while a search is active", () => {
    const html = renderCatalog(familyData(), { kind: "tool", query: "run-checks" });

    expect(html).toContain('data-catalog-family="run-checks" open');
  });
});

describe("renderSummary", () => {
  it("reports the kind's total, then the filtered count", () => {
    const data = makeData();

    expect(renderSummary(data, "cli", 2)).toBe("2 CLI commands");
    expect(renderSummary(data, "cli", 1)).toBe("Showing 1 of 2 CLI commands");
  });
});

describe("generated commands asset", () => {
  it("renders every entry and keeps names unique", () => {
    const data = commandsData as CatalogData;
    const names = data.commands.map((entry) => entry.name);

    const rendered = (["cli", "job", "tool"] as const)
      .map((kind) => renderCatalog(data, { query: "", kind }).match(/class="catalog-entry"/g)?.length ?? 0)
      .reduce((sum, count) => sum + count, 0);

    expect(new Set(names).size).toBe(names.length);
    expect(rendered).toBe(names.length);
  });
});

describe("createCatalogFeature", () => {
  const panel = (kind: string) => document.getElementById(`tab-catalog-${kind}`) as HTMLElement;
  const entriesIn = (kind: string) => panel(kind).querySelectorAll(".catalog-entry");

  beforeEach(() => {
    document.body.innerHTML = buildCatalogTemplate();
    createCatalogFeature(makeData()).wireActions();
  });

  it("renders one panel per kind, each with its own entries and summary", () => {
    expect(entriesIn("cli")).toHaveLength(2);
    expect(entriesIn("job")).toHaveLength(1);
    expect(entriesIn("tool")).toHaveLength(0);
    expect(panel("job").querySelector("[data-catalog-summary]")?.textContent).toBe("1 runtime jobs");
  });

  it("filters only the panel being searched", () => {
    const input = panel("cli").querySelector("[data-catalog-search]") as HTMLInputElement;
    input.value = "equity";
    input.dispatchEvent(new Event("input", { bubbles: true }));

    expect(entriesIn("cli")).toHaveLength(1);
    expect(entriesIn("job")).toHaveLength(1);
    expect(panel("cli").querySelector("[data-catalog-summary]")?.textContent).toBe("Showing 1 of 2 CLI commands");
  });

  it("expands and collapses every entry in its own panel", () => {
    (panel("cli").querySelector("[data-catalog-expand-all]") as HTMLButtonElement).click();
    expect(panel("cli").querySelectorAll(".catalog-entry[open]")).toHaveLength(2);
    expect(panel("job").querySelectorAll(".catalog-entry[open]")).toHaveLength(0);

    (panel("cli").querySelector("[data-catalog-collapse-all]") as HTMLButtonElement).click();
    expect(panel("cli").querySelectorAll(".catalog-entry[open]")).toHaveLength(0);
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
