import { initDocsAccordion } from "./accordion";
import { initDocsSectionLinks } from "./section-links";

export function initDocsFeature(openTab: (target: string) => void): void {
  initDocsAccordion();
  initDocsSectionLinks(openTab);
}
