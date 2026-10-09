import { find, findAll } from "./dom";

function groupOfTab(target: string): string | null {
  return find<HTMLButtonElement>(`.tab-btn[data-tab="${target}"]`)?.dataset.navGroup ?? null;
}

function tabsInGroup(group: string): string[] {
  return Array.from(findAll<HTMLButtonElement>(`.tab-btn[data-nav-group="${group}"]`))
    .map((button) => button.dataset.tab)
    .filter((tab): tab is string => Boolean(tab));
}

/** Mark the group of `target` active and show only that group's sub-row (hidden when it holds one tab). */
export function syncNav(target: string): void {
  const group = groupOfTab(target);
  for (const button of findAll<HTMLButtonElement>("[data-nav-group-target]")) {
    const isActive = button.dataset.navGroupTarget === group;
    button.classList.toggle("active", isActive);
    if (isActive) {
      button.setAttribute("aria-current", "true");
    } else {
      button.removeAttribute("aria-current");
    }
  }
  for (const subnav of findAll<HTMLElement>("[data-nav-subnav]")) {
    const name = subnav.dataset.navSubnav ?? "";
    subnav.hidden = name !== group || tabsInGroup(name).length < 2;
    if (name === group) {
      subnav.dataset.lastTab = target;
    }
  }
}

/** Open the tab the user last used in a group, or the group's first tab. */
export function initNavGroups(openTab: (target: string) => void): void {
  for (const button of findAll<HTMLButtonElement>("[data-nav-group-target]")) {
    button.addEventListener("click", () => {
      const group = button.dataset.navGroupTarget ?? "";
      const lastTab = find<HTMLElement>(`[data-nav-subnav="${group}"]`)?.dataset.lastTab;
      const target = lastTab ?? tabsInGroup(group)[0];
      if (target) {
        openTab(target);
      }
    });
  }
}
