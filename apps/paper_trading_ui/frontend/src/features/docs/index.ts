import { initDocsAccordion } from "./accordion";
import { initDocsMenu } from "./menu";

export function initDocsFeature(openTab: (target: string) => void): void {
  initDocsAccordion();
  initDocsMenu(openTab);
}
