import type { AccountDetail } from "../../types/accounts";
import { renderConfigEditor } from "./config-editor";
import { renderConfigSummary } from "./config-summary";
import type { DetailSectionName } from "./types";

export function renderConfigSection(
  detail: AccountDetail,
  options: { activeSection: DetailSectionName; showActions: boolean },
): string {
  const { activeSection, showActions } = options;
  return `
    <article class="detail-section-panel" data-detail-panel="config" ${activeSection === "config" ? "" : "hidden"}>
      <div class="config-section-head">
        <div>
          <h4>Account Configuration</h4>
          <p class="muted">Review the current account setup, then open the editor when you want to update parameters.</p>
        </div>
      </div>
      ${renderConfigEditor(detail, showActions)}
      ${renderConfigSummary(detail)}
    </article>
  `;
}
