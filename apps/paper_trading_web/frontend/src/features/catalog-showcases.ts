/** Visual cards shown at the top of a catalog group, before its rows, while the search is empty. */
import type { CatalogEntry } from "../types/catalog";
import { CHECKS_GROUP, handleCheckRunnerClick, renderCheckRunner } from "./catalog-check-runner";

const DIAGRAM_GROUP = "Data and Database";

const DIAGRAM_PREVIEW_SVG = `
  <svg class="catalog-showcase-art" viewBox="0 0 120 72" aria-hidden="true">
    <rect x="4" y="6" width="34" height="24" rx="4" />
    <rect x="82" y="6" width="34" height="24" rx="4" />
    <rect x="43" y="42" width="34" height="24" rx="4" />
    <line x1="4" y1="14" x2="38" y2="14" /><line x1="82" y1="14" x2="116" y2="14" /><line x1="43" y1="50" x2="77" y2="50" />
    <path class="catalog-showcase-art-link" d="M38 22 C 52 22, 52 54, 43 54" />
    <path class="catalog-showcase-art-link" d="M82 22 C 68 22, 68 54, 77 54" />
  </svg>`;

const DIAGRAM_SHOWCASE = `
  <div class="catalog-showcase" data-showcase="db-diagram">
    <div class="catalog-showcase-head">
      ${DIAGRAM_PREVIEW_SVG}
      <div class="catalog-showcase-text">
        <p class="catalog-showcase-kicker">Interactive</p>
        <h5 class="catalog-showcase-title">Database diagram</h5>
        <p class="catalog-showcase-copy">
          Every table, column, and foreign key, grouped by area. Built from the code-defined schema by
          <code>build-database-diagram-viewer</code>.
        </p>
        <p class="catalog-showcase-meta" data-showcase-meta hidden></p>
      </div>
      <div class="catalog-showcase-actions">
        <button type="button" class="catalog-filter active" data-showcase-toggle aria-expanded="false">Open the diagram</button>
        <a class="catalog-filter" data-showcase-fullscreen target="_blank" rel="noopener" hidden>Full screen</a>
      </div>
    </div>
    <div class="catalog-showcase-frame" data-showcase-frame hidden></div>
  </div>`;

const SHOWCASES: Record<string, (entries: CatalogEntry[]) => string> = {
  [CHECKS_GROUP]: renderCheckRunner,
  [DIAGRAM_GROUP]: () => DIAGRAM_SHOWCASE,
};

export function renderShowcase(groupName: string, entries: CatalogEntry[]): string {
  return SHOWCASES[groupName]?.(entries) ?? "";
}

/** The viewer's own "Generated: ... Tables: N." line, as shown text. */
export function describeDiagram(html: string): string {
  const match = /Generated: ([^.<]+)\. Tables: (\d+)\./.exec(html);
  return match ? `Generated ${match[1]} · ${match[2]} tables` : "";
}

async function loadDiagramHtml(): Promise<string> {
  const module = await import("../../../../../docs/reference/database-diagram-viewer.html?raw");
  return module.default;
}

async function toggleDiagram(card: HTMLElement, button: HTMLButtonElement): Promise<void> {
  const frame = card.querySelector<HTMLElement>("[data-showcase-frame]");
  if (!frame) {
    return;
  }
  const opening = frame.hidden;
  if (opening && !frame.querySelector("iframe")) {
    button.disabled = true;
    button.textContent = "Loading...";
    try {
      const html = await loadDiagramHtml();
      const iframe = document.createElement("iframe");
      iframe.title = "Database diagram viewer";
      iframe.srcdoc = html;
      frame.appendChild(iframe);

      const fullscreen = card.querySelector<HTMLAnchorElement>("[data-showcase-fullscreen]");
      if (fullscreen) {
        fullscreen.href = URL.createObjectURL(new Blob([html], { type: "text/html" }));
        fullscreen.hidden = false;
      }
      const meta = card.querySelector<HTMLElement>("[data-showcase-meta]");
      if (meta) {
        meta.textContent = describeDiagram(html);
        meta.hidden = meta.textContent === "";
      }
    } catch {
      button.textContent = "Could not load the diagram";
      return;
    } finally {
      button.disabled = false;
    }
  }
  frame.hidden = !opening;
  button.textContent = opening ? "Hide the diagram" : "Open the diagram";
  button.setAttribute("aria-expanded", String(opening));
}

/** Handle a click inside a catalog panel; returns true when a showcase control took it. */
export function handleShowcaseClick(target: HTMLElement): boolean {
  if (handleCheckRunnerClick(target)) {
    return true;
  }
  const toggle = target.closest<HTMLButtonElement>("[data-showcase-toggle]");
  const card = toggle?.closest<HTMLElement>('[data-showcase="db-diagram"]');
  if (!toggle || !card) {
    return false;
  }
  void toggleDiagram(card, toggle);
  return true;
}
