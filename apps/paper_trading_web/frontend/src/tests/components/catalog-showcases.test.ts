import { describe, expect, it } from "vitest";

import { renderCatalog } from "../../features/catalog";
import { describeDiagram, renderShowcase } from "../../features/catalog-showcases";
import type { CatalogData, CatalogEntry } from "../../types/catalog";

function tool(name: string, group: string): CatalogEntry {
  return {
    name,
    kind: "tool",
    group,
    family: null,
    risk: "read-only",
    module: null,
    schedule: null,
    runnable: false,
    help: "Help.",
    example: `python -m ${name}`,
    arguments: [],
  };
}

const data: CatalogData = {
  schema_version: 3,
  cli_invocation: "python -m app",
  groups: [
    { name: "Quality Checks", kind: "tool" },
    { name: "Data and Database", kind: "tool" },
  ],
  families: [],
  commands: [tool("lint", "Quality Checks"), tool("describe-db-schema", "Data and Database")],
};

describe("catalog showcases", () => {
  it("renders the diagram card only for its group", () => {
    expect(renderShowcase("Data and Database")).toContain('data-showcase="db-diagram"');
    expect(renderShowcase("Quality Checks")).toBe("");
  });

  it("puts the card before the group's rows and hides it during a search", () => {
    const html = renderCatalog(data, { query: "", kind: "tool" });
    expect(html.indexOf('data-showcase="db-diagram"')).toBeLessThan(
      html.indexOf('data-catalog-entry="describe-db-schema"'),
    );

    expect(renderCatalog(data, { query: "describe", kind: "tool" })).not.toContain("data-showcase");
  });

  it("reads the build date and table count from the viewer", () => {
    expect(describeDiagram("<div>Source: x. Generated: 20:00 01-10-2026 PST. Tables: 28.</div>")).toBe(
      "Generated 20:00 01-10-2026 PST · 28 tables",
    );
    expect(describeDiagram("<html></html>")).toBe("");
  });
});
