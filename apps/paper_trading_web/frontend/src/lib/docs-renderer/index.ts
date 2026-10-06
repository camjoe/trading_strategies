import { buildApiCard } from "./api";
import { buildFinanceCard } from "./finance";
import { buildSoftwareCard } from "./software";

function docsPanel(tab: string, card: string): string {
  return `<div id="tab-${tab}" class="tab-panel layout docs-panel" hidden>
${card}
</div>`;
}

export function buildDocsTemplate(): string {
  return [
    docsPanel("docs-markets", buildFinanceCard()),
    docsPanel("docs-software", buildSoftwareCard()),
    docsPanel("docs-api", buildApiCard()),
  ].join("\n\n");
}
