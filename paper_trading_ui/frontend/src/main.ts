import "./styles.css";
import { find } from "./lib/dom";
import { createAccountsFeature } from "./features/accounts";
import { createBacktestingFeature } from "./features/backtesting";
import { createLogsFeature } from "./features/logs";
import shellTemplate from "./templates/shell.html?raw";

const appRoot = find<HTMLDivElement>("#app");
if (!appRoot) {
  throw new Error("Missing #app root");
}
const app = appRoot;

type DocsSectionLink = {
  groupLabel: string;
  sectionId: string;
  sectionTitle: string;
};

type DocsSectionButtonIndex = Map<string, HTMLButtonElement[]>;

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function openTab(target: string): void {
  const tabBtns = document.querySelectorAll<HTMLButtonElement>(".tab-btn");
  const tabPanels = document.querySelectorAll<HTMLElement>(".tab-panel");

  tabBtns.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === target);
  });
  tabPanels.forEach((panel) => {
    panel.hidden = panel.id !== `tab-${target}`;
  });
}

function renderShell(): void {
  app.innerHTML = shellTemplate;
}

function scrollToDocsSection(sectionId: string): void {
  openTab("docs");
  requestAnimationFrame(() => {
    document.getElementById(sectionId)?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

function collectDocsSections(): DocsSectionLink[] {
  const sectionHeadings = Array.from(
    document.querySelectorAll<HTMLHeadingElement>("#tab-docs .ref-card .ref-section > h3"),
  );

  return sectionHeadings.flatMap((heading) => {
    const section = heading.closest<HTMLElement>(".ref-section");
    const card = heading.closest<HTMLElement>(".ref-card");
    const groupHeading = card?.querySelector<HTMLHeadingElement>("h2");
    const sectionTitle = heading.textContent?.trim();
    const groupLabel = groupHeading?.textContent?.trim();

    if (!section || !sectionTitle || !groupLabel) {
      return [];
    }

    if (!section.id) {
      section.id = `docs-${slugify(sectionTitle)}`;
    }

    return [
      {
        groupLabel,
        sectionId: section.id,
        sectionTitle,
      },
    ];
  });
}

function renderDocsSectionGroups(
  container: HTMLElement,
  sections: DocsSectionLink[],
  itemClassName: string,
): DocsSectionButtonIndex {
  const groups = new Map<string, DocsSectionLink[]>();
  const buttonsBySection = new Map<string, HTMLButtonElement[]>();

  sections.forEach((section) => {
    const items = groups.get(section.groupLabel) ?? [];
    items.push(section);
    groups.set(section.groupLabel, items);
  });

  groups.forEach((items, groupLabel) => {
    const group = document.createElement("section");
    group.className = "docs-link-group";

    const label = document.createElement("h3");
    label.className = "docs-link-group-title";
    label.textContent = groupLabel;
    group.appendChild(label);

    const list = document.createElement("div");
    list.className = "docs-link-group-list";

    items.forEach((section) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = itemClassName;
      item.textContent = section.sectionTitle;
      item.dataset.sectionId = section.sectionId;
      item.addEventListener("click", () => {
        scrollToDocsSection(section.sectionId);
      });
      list.appendChild(item);

      const sectionButtons = buttonsBySection.get(section.sectionId) ?? [];
      sectionButtons.push(item);
      buttonsBySection.set(section.sectionId, sectionButtons);
    });

    group.appendChild(list);
    container.appendChild(group);
  });

  return buttonsBySection;
}

function setActiveDocsSection(buttonsBySection: DocsSectionButtonIndex, activeSectionId: string): void {
  buttonsBySection.forEach((buttons, sectionId) => {
    const isActive = sectionId === activeSectionId;
    buttons.forEach((button) => {
      button.classList.toggle("active", isActive);
      if (isActive) {
        button.setAttribute("aria-current", "true");
      } else {
        button.removeAttribute("aria-current");
      }
    });
  });
}

const backtestingFeature = createBacktestingFeature();
const accountsFeature = createAccountsFeature({
  onAccountsLoaded: (accounts) => {
    backtestingFeature.setAccounts(accounts);
  },
  onOpenRunReport: (runId) => backtestingFeature.loadBacktestReport(runId),
});
const logsFeature = createLogsFeature();

async function bootstrap(): Promise<void> {
  renderShell();
  initTabs();
  initDocsMenu();
  accountsFeature.wireActions();
  logsFeature.wireActions();
  backtestingFeature.wireActions();
  await accountsFeature.loadAccounts();
  await logsFeature.loadLogFiles();
  await backtestingFeature.loadBacktestRuns();
}

function initTabs(): void {
  const tabBtns = document.querySelectorAll<HTMLButtonElement>(".tab-btn");

  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.tab;
      if (!target) {
        return;
      }
      openTab(target);
    });
  });
}

function initDocsMenu(): void {
  const docsNavItem = find<HTMLElement>("#docsNavItem");
  const docsTabBtn = find<HTMLButtonElement>("#docsTabBtn");
  const docsSectionMenu = find<HTMLElement>("#docsSectionMenu");
  const docsSectionList = find<HTMLElement>("#docsSectionList");
  const sections = collectDocsSections();

  if (!docsNavItem || !docsTabBtn || !docsSectionMenu || !docsSectionList || sections.length === 0) {
    return;
  }

  let closeMenuTimeoutId: number | undefined;
  const sectionElements = sections.flatMap((section) => {
    const element = document.getElementById(section.sectionId);
    return element ? [{ ...section, element }] : [];
  });

  const clearCloseMenuTimeout = () => {
    if (closeMenuTimeoutId !== undefined) {
      window.clearTimeout(closeMenuTimeoutId);
      closeMenuTimeoutId = undefined;
    }
  };

  const setMenuOpen = (isOpen: boolean) => {
    clearCloseMenuTimeout();
    docsSectionMenu.hidden = !isOpen;
    docsNavItem.classList.toggle("open", isOpen);
    docsTabBtn.setAttribute("aria-expanded", String(isOpen));
  };

  const queueMenuClose = () => {
    clearCloseMenuTimeout();
    closeMenuTimeoutId = window.setTimeout(() => {
      docsSectionMenu.hidden = true;
      docsNavItem.classList.remove("open");
      docsTabBtn.setAttribute("aria-expanded", "false");
      closeMenuTimeoutId = undefined;
    }, 140);
  };

  const allButtons = renderDocsSectionGroups(docsSectionList, sections, "docs-nav-item");

  const updateActiveSection = () => {
    if (!document.querySelector<HTMLElement>("#tab-docs:not([hidden])") || sectionElements.length === 0) {
      return;
    }

    const anchorOffset = 170;
    let activeSectionId = sectionElements[0].sectionId;

    sectionElements.forEach((section) => {
      if (section.element.getBoundingClientRect().top <= anchorOffset) {
        activeSectionId = section.sectionId;
      }
    });

    setActiveDocsSection(allButtons, activeSectionId);
  };

  if (sectionElements.length > 0) {
    setActiveDocsSection(allButtons, sectionElements[0].sectionId);
  }

  docsSectionList.addEventListener("click", () => {
    setMenuOpen(false);
  });

  docsNavItem.addEventListener("mouseenter", () => {
    setMenuOpen(true);
  });

  docsNavItem.addEventListener("mouseleave", () => {
    queueMenuClose();
  });

  docsTabBtn.addEventListener("click", () => {
    setMenuOpen(false);
    requestAnimationFrame(updateActiveSection);
  });

  docsNavItem.addEventListener("focusout", (event) => {
    const nextTarget = event.relatedTarget;
    if (!(nextTarget instanceof Node && docsNavItem.contains(nextTarget))) {
      queueMenuClose();
    }
  });

  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Node) || docsNavItem.contains(event.target)) {
      return;
    }
    setMenuOpen(false);
  });

  window.addEventListener("scroll", updateActiveSection, { passive: true });
  window.addEventListener("resize", updateActiveSection);
}

void bootstrap();
