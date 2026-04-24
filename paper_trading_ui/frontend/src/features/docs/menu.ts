import { find, findAll } from "../../lib/dom";
import { getDocsGroupDisplayLabel } from "./constants";
import { scrollToDocsSection } from "./accordion";
import { slugify } from "./helpers";
import type { DocsSectionButtonIndex, DocsSectionElementLink, DocsSectionLink } from "./types";

function collectDocsSections(): DocsSectionLink[] {
  const sectionHeadings = Array.from(
    document.querySelectorAll<HTMLHeadingElement>("#tab-docs .ref-card .ref-section > h3"),
  );

  return sectionHeadings
    .map((heading) => {
      const section = heading.closest<HTMLElement>(".ref-section");
      const card = heading.closest<HTMLElement>(".ref-card");
      const groupHeading = card?.querySelector<HTMLHeadingElement>("h2");
      const sectionTitle = heading.textContent?.trim();
      const groupLabel = groupHeading?.textContent?.trim();

      if (!section || !sectionTitle || !groupLabel) {
        return null;
      }

      if (!section.id) {
        section.id = `docs-${slugify(sectionTitle)}`;
      }

      return {
        groupLabel,
        sectionId: section.id,
        sectionTitle,
      };
    })
    .filter((item): item is DocsSectionLink => item !== null);
}

function collectDocsSectionElements(sections: DocsSectionLink[]): DocsSectionElementLink[] {
  return sections.flatMap((section) => {
    const element = document.getElementById(section.sectionId);
    return element ? [{ ...section, element }] : [];
  });
}

function renderDocsSectionFlyout(
  container: HTMLElement,
  sections: DocsSectionLink[],
  openTab: (target: string) => void,
): DocsSectionButtonIndex {
  const groups = new Map<string, DocsSectionLink[]>();
  const groupOrder: string[] = [];
  const groupButtons = new Map<string, HTMLButtonElement>();
  const groupPanels = new Map<string, HTMLElement>();
  const buttonsBySection = new Map<string, HTMLButtonElement[]>();

  sections.forEach((section) => {
    if (!groups.has(section.groupLabel)) {
      groups.set(section.groupLabel, []);
      groupOrder.push(section.groupLabel);
    }
    groups.get(section.groupLabel)?.push(section);
  });

  const root = document.createElement("div");
  root.className = "docs-nav-two-pane";

  const primaryList = document.createElement("div");
  primaryList.className = "docs-nav-primary-list";

  const secondary = document.createElement("div");
  secondary.className = "docs-nav-secondary";
  secondary.hidden = true;

  const setActiveGroup = (groupLabel: string) => {
    root.classList.add("has-secondary");
    secondary.hidden = false;

    groupButtons.forEach((button, label) => {
      const isActive = label === groupLabel;
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-expanded", String(isActive));
    });

    groupPanels.forEach((panel, label) => {
      panel.hidden = label !== groupLabel;
    });
  };

  groupOrder.forEach((groupLabel) => {
    const groupDisplayLabel = getDocsGroupDisplayLabel(groupLabel);

    const primaryItem = document.createElement("button");
    primaryItem.type = "button";
    primaryItem.className = "docs-nav-group-item";
    primaryItem.textContent = groupDisplayLabel;
    primaryItem.dataset.group = groupLabel;

    primaryItem.addEventListener("mouseenter", () => {
      setActiveGroup(groupLabel);
    });
    primaryItem.addEventListener("focus", () => {
      setActiveGroup(groupLabel);
    });

    primaryList.appendChild(primaryItem);
    groupButtons.set(groupLabel, primaryItem);

    const panel = document.createElement("section");
    panel.className = "docs-nav-secondary-panel";
    panel.hidden = true;

    const panelTitle = document.createElement("h3");
    panelTitle.className = "docs-link-group-title";
    panelTitle.textContent = groupDisplayLabel;
    panel.appendChild(panelTitle);

    const panelList = document.createElement("div");
    panelList.className = "docs-link-group-list";

    (groups.get(groupLabel) ?? []).forEach((section) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "docs-nav-item";
      item.textContent = section.sectionTitle;
      item.dataset.sectionId = section.sectionId;
      item.addEventListener("click", () => {
        scrollToDocsSection(section.sectionId, openTab);
      });
      panelList.appendChild(item);

      const sectionButtons = buttonsBySection.get(section.sectionId) ?? [];
      sectionButtons.push(item);
      buttonsBySection.set(section.sectionId, sectionButtons);
    });

    panel.appendChild(panelList);
    secondary.appendChild(panel);
    groupPanels.set(groupLabel, panel);
  });

  root.appendChild(primaryList);
  root.appendChild(secondary);
  container.appendChild(root);

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

export function initDocsMenu(openTab: (target: string) => void): void {
  const docsNavItem = find<HTMLElement>("#docsNavItem");
  const docsTabBtn = find<HTMLButtonElement>("#docsTabBtn");
  const docsSectionMenu = find<HTMLElement>("#docsSectionMenu");
  const docsSectionList = find<HTMLElement>("#docsSectionList");
  const sections = collectDocsSections();

  if (!docsNavItem || !docsTabBtn || !docsSectionMenu || !docsSectionList || sections.length === 0) {
    return;
  }

  let closeMenuTimeoutId: number | undefined;
  const sectionElements = collectDocsSectionElements(sections);

  const clearCloseMenuTimeout = () => {
    if (closeMenuTimeoutId !== undefined) {
      window.clearTimeout(closeMenuTimeoutId);
      closeMenuTimeoutId = undefined;
    }
  };

  const resetFlyoutState = () => {
    const flyoutRoot = docsSectionList.querySelector<HTMLElement>(".docs-nav-two-pane");
    const secondaryPane = docsSectionList.querySelector<HTMLElement>(".docs-nav-secondary");

    flyoutRoot?.classList.remove("has-secondary");
    if (secondaryPane) {
      secondaryPane.hidden = true;
    }

    findAll<HTMLButtonElement>(".docs-nav-group-item", docsSectionList).forEach((button) => {
      button.classList.remove("active");
      button.setAttribute("aria-expanded", "false");
    });
    findAll<HTMLElement>(".docs-nav-secondary-panel", docsSectionList).forEach((panel) => {
      panel.hidden = true;
    });
  };

  const setMenuOpen = (isOpen: boolean) => {
    clearCloseMenuTimeout();
    if (isOpen) {
      resetFlyoutState();
    }
    docsSectionMenu.hidden = !isOpen;
    docsNavItem.classList.toggle("open", isOpen);
    docsTabBtn.setAttribute("aria-expanded", String(isOpen));
  };

  const closeMenu = () => {
    setMenuOpen(false);
  };

  const queueMenuClose = () => {
    clearCloseMenuTimeout();
    closeMenuTimeoutId = window.setTimeout(() => {
      closeMenu();
      closeMenuTimeoutId = undefined;
    }, 140);
  };

  const allButtons = renderDocsSectionFlyout(docsSectionList, sections, openTab);

  const updateActiveSection = () => {
    if (!find<HTMLElement>("#tab-docs:not([hidden])") || sectionElements.length === 0) {
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
    closeMenu();
  });

  docsNavItem.addEventListener("mouseenter", () => {
    setMenuOpen(true);
  });

  docsNavItem.addEventListener("mouseleave", () => {
    queueMenuClose();
  });

  docsTabBtn.addEventListener("click", () => {
    closeMenu();
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
    closeMenu();
  });

  window.addEventListener("scroll", updateActiveSection, { passive: true });
  window.addEventListener("resize", updateActiveSection);
}
