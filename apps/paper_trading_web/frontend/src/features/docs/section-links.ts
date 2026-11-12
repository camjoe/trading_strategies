import { findAll } from "../../lib/dom";
import { esc } from "../../lib/format";
import { scrollToDocsSection } from "./accordion";

/** Add a row of links under each docs card heading; a link opens and scrolls to its section. */
export function initDocsSectionLinks(openTab: (target: string) => void): void {
  for (const card of findAll<HTMLElement>(".docs-panel .ref-card")) {
    const sections = Array.from(card.querySelectorAll<HTMLElement>(":scope > .ref-section[id]"));
    const head = card.querySelector<HTMLElement>(":scope > .ref-card-head");
    if (!sections.length || !head) {
      continue;
    }
    const links = sections
      .map((section) => {
        const title = section.querySelector(":scope > h3")?.textContent?.trim() ?? section.id;
        return `<button type="button" class="docs-section-link" data-docs-section="${esc(section.id)}">${esc(title)}</button>`;
      })
      .join("");
    head.insertAdjacentHTML(
      "afterend",
      `<nav class="docs-section-links" aria-label="Sections">${links}</nav>`,
    );
  }

  for (const nav of findAll<HTMLElement>(".docs-section-links")) {
    nav.addEventListener("click", (event) => {
      const link = (event.target as HTMLElement).closest<HTMLElement>("[data-docs-section]");
      if (link?.dataset.docsSection) {
        scrollToDocsSection(link.dataset.docsSection, openTab);
      }
    });
  }
}
