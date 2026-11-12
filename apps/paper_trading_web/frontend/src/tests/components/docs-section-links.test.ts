// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

import { initDocsFeature } from "../../features/docs";
import { buildDocsTemplate } from "../../lib/docs-renderer";

describe("docs section links", () => {
  const openTab = vi.fn();

  beforeEach(() => {
    openTab.mockClear();
    Element.prototype.scrollIntoView = vi.fn();
    document.body.innerHTML = buildDocsTemplate();
    initDocsFeature(openTab);
  });

  it("adds one link per section under each card heading", () => {
    for (const panel of document.querySelectorAll<HTMLElement>(".docs-panel")) {
      const sections = panel.querySelectorAll(".ref-card > .ref-section");
      const links = panel.querySelectorAll(".docs-section-links [data-docs-section]");

      expect(sections.length).toBeGreaterThan(0);
      expect(links).toHaveLength(sections.length);
    }
  });

  it("opens the section's own tab and expands only that section", () => {
    const panel = document.getElementById("tab-docs-software") as HTMLElement;
    const link = panel.querySelector<HTMLButtonElement>("[data-docs-section]") as HTMLButtonElement;
    const sectionId = link.dataset.docsSection as string;

    link.click();

    expect(openTab).toHaveBeenCalledWith("docs-software");
    expect(document.getElementById(sectionId)?.classList.contains("expanded")).toBe(true);
    expect(panel.querySelectorAll(".ref-section.expanded")).toHaveLength(1);
  });
});
