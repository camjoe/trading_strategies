import { esc } from "../lib/format";
import type { ParameterGroup } from "../features/admin/types";

export function renderParameterGroups(
  groups: ParameterGroup[],
  search: string,
  source: string,
): { html: string; groupCount: number; entryCount: number } {
  const needle = search.trim().toLowerCase();
  const filtered = groups.flatMap(group => {
    const scopeMatches = group.scope.toLowerCase().includes(needle);
    const entries = group.entries.filter(entry =>
      (!source || entry.source === source)
      && (!needle || scopeMatches || entry.name.toLowerCase().includes(needle) || entry.value.toLowerCase().includes(needle)),
    );
    return entries.length ? [{ ...group, entries }] : [];
  });
  const entryCount = filtered.reduce((total, group) => total + group.entries.length, 0);
  if (!filtered.length) {
    return { html: '<div class="empty">No parameters match the current filters.</div>', groupCount: 0, entryCount: 0 };
  }
  return {
    groupCount: filtered.length,
    entryCount,
    html: filtered.map(group => `
      <section class="config-summary-card parameter-group-card">
        <div class="ops-card-head">
          <h3>${esc(group.scope)}</h3>
          <span class="status-pill ${group.note ? "warning" : "ok"}">${group.note ? "defaults active" : "resolved"}</span>
        </div>
        ${group.note ? `<p class="admin-note">${esc(group.note)}</p>` : ""}
        <table class="ref-table">
          <thead><tr><th>Parameter</th><th>Effective value</th><th>Source</th></tr></thead>
          <tbody>${group.entries.map(entry => `
            <tr>
              <td><code>${esc(entry.name)}</code></td>
              <td><code>${esc(entry.value)}</code></td>
              <td><span class="chip">${esc(entry.source)}</span></td>
            </tr>`).join("")}
          </tbody>
        </table>
      </section>`).join(""),
  };
}
