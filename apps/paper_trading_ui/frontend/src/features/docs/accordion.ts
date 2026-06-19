import { COLLAPSE_ALL_ICON, EXPAND_ALL_ICON } from "./constants";
import { slugify } from "./helpers";

function setDocsSectionExpanded(section: HTMLElement, expanded: boolean): void {
  const button = section.querySelector<HTMLButtonElement>(":scope > h3 .ref-section-toggle");
  const body = section.querySelector<HTMLElement>(":scope > .ref-section-body");

  section.classList.toggle("expanded", expanded);
  button?.setAttribute("aria-expanded", String(expanded));
  if (button) {
    if (!expanded) {
      button.setAttribute("title", "click to expand");
    } else {
      button.removeAttribute("title");
    }
  }
  if (body) {
    body.hidden = !expanded;
  }
}

function expandDocsSection(sectionId: string): void {
  const section = document.getElementById(sectionId);
  const card = section?.closest<HTMLElement>(".ref-card");
  if (!section || !card) {
    return;
  }

  const siblingSections = Array.from(card.querySelectorAll<HTMLElement>(":scope .ref-section"));
  siblingSections.forEach((sibling) => {
    setDocsSectionExpanded(sibling, sibling === section);
  });
}

export function scrollToDocsSection(sectionId: string, openTab: (target: string) => void): void {
  openTab("docs");
  expandDocsSection(sectionId);
  requestAnimationFrame(() => {
    document.getElementById(sectionId)?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

export function initDocsAccordion(): void {
  const cards = Array.from(document.querySelectorAll<HTMLElement>("#tab-docs .ref-card"));

  cards.forEach((card) => {
    const cardToggleAllBtn = card.querySelector<HTMLButtonElement>("[data-ref-card-toggle-all]");
    const sections = Array.from(card.querySelectorAll<HTMLElement>(":scope > .ref-section"));

    const updateCardToggleAllButton = () => {
      if (!cardToggleAllBtn) {
        return;
      }

      const allExpanded = sections.length > 0 && sections.every((section) => section.classList.contains("expanded"));
      const label = allExpanded ? "Collapse all" : "Expand all";
      cardToggleAllBtn.textContent = allExpanded ? COLLAPSE_ALL_ICON : EXPAND_ALL_ICON;
      cardToggleAllBtn.setAttribute("aria-label", label);
      cardToggleAllBtn.setAttribute("data-tooltip", label);
    };

    sections.forEach((section) => {
      const heading = section.querySelector<HTMLHeadingElement>(":scope > h3");
      if (!heading) {
        return;
      }

      const sectionTitle = heading.textContent?.trim() ?? "Section";
      if (!section.id) {
        section.id = `docs-${slugify(sectionTitle)}`;
      }

      const body = document.createElement("div");
      body.className = "ref-section-body";
      body.id = `${section.id}-content`;

      while (heading.nextSibling) {
        body.appendChild(heading.nextSibling);
      }

      const button = document.createElement("button");
      button.type = "button";
      button.className = "ref-section-toggle";
      button.textContent = sectionTitle;
      button.setAttribute("aria-controls", body.id);

      heading.textContent = "";
      heading.classList.add("ref-section-heading");
      heading.appendChild(button);
      section.appendChild(body);

      const setExpanded = (expanded: boolean) => {
        if (expanded) {
          sections.forEach((sibling) => {
            setDocsSectionExpanded(sibling, sibling === section);
          });
          updateCardToggleAllButton();
          return;
        }

        setDocsSectionExpanded(section, false);
        updateCardToggleAllButton();
      };

      button.addEventListener("click", () => {
        setExpanded(!section.classList.contains("expanded"));
      });

      setDocsSectionExpanded(section, false);
    });

    if (cardToggleAllBtn) {
      cardToggleAllBtn.addEventListener("click", () => {
        const shouldExpandAll = !sections.every((section) => section.classList.contains("expanded"));
        sections.forEach((section) => {
          setDocsSectionExpanded(section, shouldExpandAll);
        });
        updateCardToggleAllButton();
      });
    }

    updateCardToggleAllButton();
  });
}
