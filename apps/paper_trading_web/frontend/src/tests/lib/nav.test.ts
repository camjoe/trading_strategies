// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

import { initNavGroups, syncNav } from "../../lib/nav";
import navTemplate from "../../views/nav.html?raw";

function visibleSubnavs(): string[] {
  return Array.from(document.querySelectorAll<HTMLElement>("[data-nav-subnav]"))
    .filter((subnav) => !subnav.hidden)
    .map((subnav) => subnav.dataset.navSubnav ?? "");
}

function activeGroups(): string[] {
  return Array.from(document.querySelectorAll<HTMLElement>(".nav-group-btn.active")).map(
    (button) => button.dataset.navGroupTarget ?? "",
  );
}

describe("nav groups", () => {
  beforeEach(() => {
    document.body.innerHTML = navTemplate;
  });

  it("every tab button except the direct system tabs belongs to a group", () => {
    const ungrouped = Array.from(document.querySelectorAll<HTMLButtonElement>(".tab-btn"))
      .filter((button) => !button.dataset.navGroup)
      .map((button) => button.dataset.tab);

    expect(ungrouped).toEqual(["docs", "admin"]);
  });

  it("every group button has a sub-row and every sub-tab names an existing group", () => {
    const groups = Array.from(document.querySelectorAll<HTMLElement>("[data-nav-group-target]")).map(
      (button) => button.dataset.navGroupTarget,
    );
    const subnavs = Array.from(document.querySelectorAll<HTMLElement>("[data-nav-subnav]")).map(
      (subnav) => subnav.dataset.navSubnav,
    );
    const tabGroups = new Set(
      Array.from(document.querySelectorAll<HTMLElement>(".tab-btn[data-nav-group]")).map(
        (button) => button.dataset.navGroup,
      ),
    );

    expect(subnavs).toEqual(groups);
    expect([...tabGroups].sort()).toEqual([...groups].sort());
  });

  it("shows the sub-row and active group of the opened tab", () => {
    syncNav("strategy-lab");

    expect(activeGroups()).toEqual(["research"]);
    expect(visibleSubnavs()).toEqual(["research"]);
  });

  it("hides the sub-row for a group with one tab", () => {
    syncNav("catalog");

    expect(activeGroups()).toEqual(["catalog"]);
    expect(visibleSubnavs()).toEqual([]);
  });

  it("clears the active group and sub-row for the direct system tabs", () => {
    syncNav("accounts");
    syncNav("admin");

    expect(activeGroups()).toEqual([]);
    expect(visibleSubnavs()).toEqual([]);
  });

  it("opens the first tab of a group, then the last tab used in it", () => {
    const openTab = vi.fn((target: string) => syncNav(target));
    initNavGroups(openTab);
    const groupButton = (group: string) =>
      document.querySelector<HTMLButtonElement>(`[data-nav-group-target="${group}"]`);

    groupButton("research")?.click();
    expect(openTab).toHaveBeenLastCalledWith("backtesting");

    syncNav("alt-strategies");
    groupButton("operate")?.click();
    groupButton("research")?.click();
    expect(openTab).toHaveBeenLastCalledWith("alt-strategies");
  });
});
