import { buildApiCard } from "./api";
import { buildFinanceCard } from "./finance";
import { buildSoftwareCard } from "./software";

export function buildDocsTemplate(): string {
  return `<div id="tab-docs" class="tab-panel layout" hidden>
${buildFinanceCard()}

${buildSoftwareCard()}

${buildApiCard()}
</div>`;
}
