import commandsData from "../assets/commands.json";
import { find, findAll } from "../lib/dom";
import { esc } from "../lib/format";
import type {
  CatalogArgument,
  CatalogData,
  CatalogEntry,
  CatalogFilter,
  CatalogKind,
  CatalogRisk,
} from "../types/catalog";

export interface CatalogFeature {
  wireActions: () => void;
}

export const KIND_LABELS: Record<CatalogKind, string> = {
  cli: "CLI commands",
  job: "Runtime jobs",
  tool: "Scripts and tools",
};

const COUNT_LABELS: Record<CatalogKind, string> = {
  cli: "CLI commands",
  job: "runtime jobs",
  tool: "scripts and tools",
};

export const RISK_LABELS: Record<CatalogRisk, string> = {
  "read-only": "Read-only",
  "writes-local": "Writes local data",
  broker: "Broker",
};

const RISK_PILL_CLASS: Record<CatalogRisk, string> = {
  "read-only": "ok",
  "writes-local": "warning",
  broker: "missing",
};

const RISK_HINTS: Record<CatalogRisk, string> = {
  "read-only": "Changes no trading data.",
  "writes-local": "Writes to the local database, logs, or files.",
  broker: "Can submit or reconcile broker orders.",
};

export const DEFAULT_FILTER: CatalogFilter = { query: "", kind: "all", risk: "all" };

function searchText(entry: CatalogEntry): string {
  const argumentText = entry.arguments.flatMap((argument) => [...argument.flags, argument.help]);
  return [entry.name, entry.help, entry.group, entry.module ?? "", ...argumentText].join(" ").toLowerCase();
}

export function filterEntries(entries: CatalogEntry[], filter: CatalogFilter): CatalogEntry[] {
  const terms = filter.query.toLowerCase().split(/\s+/).filter(Boolean);
  return entries.filter((entry) => {
    if (filter.kind !== "all" && entry.kind !== filter.kind) {
      return false;
    }
    if (filter.risk !== "all" && entry.risk !== filter.risk) {
      return false;
    }
    const haystack = searchText(entry);
    return terms.every((term) => haystack.includes(term));
  });
}

export function formatDefault(value: unknown): string {
  if (value === null || value === undefined || value === false || value === "") {
    return "";
  }
  return Array.isArray(value) ? value.join(", ") : String(value);
}

function renderArgumentRow(argument: CatalogArgument): string {
  const flags = argument.flags.map((flag) => `<code>${esc(flag)}</code>`).join(" ");
  const requirement = argument.required ? `<span class="catalog-required">required</span>` : "optional";
  const choices = argument.choices ? `<div class="catalog-choices">Choices: ${esc(argument.choices.join(", "))}</div>` : "";
  const defaultValue = formatDefault(argument.default);
  return `
    <tr>
      <td>${flags}</td>
      <td>${esc(argument.type)}</td>
      <td>${requirement}</td>
      <td>${defaultValue ? `<code>${esc(defaultValue)}</code>` : ""}</td>
      <td>${esc(argument.help)}${choices}</td>
    </tr>
  `;
}

function renderArguments(entry: CatalogEntry): string {
  if (!entry.arguments.length) {
    return `<p class="catalog-no-arguments">Takes no arguments.</p>`;
  }
  return `
    <div class="catalog-table-wrap">
      <table class="catalog-table">
        <thead>
          <tr><th>Argument</th><th>Type</th><th>Use</th><th>Default</th><th>Description</th></tr>
        </thead>
        <tbody>${entry.arguments.map(renderArgumentRow).join("")}</tbody>
      </table>
    </div>
  `;
}

export function renderEntry(entry: CatalogEntry): string {
  const schedule = entry.schedule ? `<span class="chip">${esc(entry.schedule)}</span>` : "";
  return `
    <details class="catalog-entry" data-catalog-entry="${esc(entry.name)}">
      <summary>
        <span class="catalog-entry-name"><code>${esc(entry.name)}</code></span>
        <span class="catalog-entry-help">${esc(entry.help)}</span>
        <span class="catalog-entry-tags">
          ${schedule}
          <span class="status-pill ${RISK_PILL_CLASS[entry.risk]}" title="${esc(RISK_HINTS[entry.risk])}">${esc(RISK_LABELS[entry.risk])}</span>
        </span>
      </summary>
      <div class="catalog-entry-body">
        <div class="catalog-example">
          <code>${esc(entry.example)}</code>
          <button type="button" class="catalog-filter catalog-copy-btn" data-catalog-copy="${esc(entry.example)}">Copy</button>
        </div>
        ${renderArguments(entry)}
      </div>
    </details>
  `;
}

function renderGroup(groupName: string, entries: CatalogEntry[]): string {
  return `
    <section class="catalog-group">
      <h4 class="catalog-group-title">${esc(groupName)} <span class="catalog-count">${entries.length}</span></h4>
      ${entries.map(renderEntry).join("")}
    </section>
  `;
}

export function renderCatalog(data: CatalogData, filter: CatalogFilter): string {
  const matches = filterEntries(data.commands, filter);
  if (!matches.length) {
    return `<div class="empty">No commands match the current filters.</div>`;
  }

  const sections = (Object.keys(KIND_LABELS) as CatalogKind[])
    .map((kind) => {
      const kindEntries = matches.filter((entry) => entry.kind === kind);
      if (!kindEntries.length) {
        return "";
      }
      const groups = data.groups
        .filter((group) => group.kind === kind)
        .map((group) => ({ name: group.name, entries: kindEntries.filter((entry) => entry.group === group.name) }))
        .filter((group) => group.entries.length);
      return `
        <div class="catalog-kind">
          <h3 class="catalog-kind-title">${esc(KIND_LABELS[kind])}</h3>
          ${groups.map((group) => renderGroup(group.name, group.entries)).join("")}
        </div>
      `;
    })
    .join("");
  return sections;
}

export function renderSummary(data: CatalogData, shown: number): string {
  const total = data.commands.length;
  const counts = (Object.keys(KIND_LABELS) as CatalogKind[])
    .map((kind) => `${data.commands.filter((entry) => entry.kind === kind).length} ${COUNT_LABELS[kind]}`)
    .join(" · ");
  return shown === total ? `${total} entries: ${counts}` : `Showing ${shown} of ${total} entries`;
}

export function createCatalogFeature(data: CatalogData = commandsData as CatalogData): CatalogFeature {
  const filter: CatalogFilter = { ...DEFAULT_FILTER };

  function render(): void {
    const list = find<HTMLElement>("#catalogList");
    const summary = find<HTMLElement>("#catalogSummary");
    if (!list || !summary) {
      return;
    }
    list.innerHTML = renderCatalog(data, filter);
    summary.textContent = renderSummary(data, filterEntries(data.commands, filter).length);
    for (const button of findAll<HTMLButtonElement>("[data-catalog-kind]")) {
      button.classList.toggle("active", button.dataset.catalogKind === filter.kind);
    }
    for (const button of findAll<HTMLButtonElement>("[data-catalog-risk]")) {
      button.classList.toggle("active", button.dataset.catalogRisk === filter.risk);
    }
  }

  function setAllOpen(open: boolean): void {
    for (const entry of findAll<HTMLDetailsElement>("#catalogList .catalog-entry")) {
      entry.open = open;
    }
  }

  async function copyExample(button: HTMLButtonElement): Promise<void> {
    const text = button.dataset.catalogCopy ?? "";
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "Copied";
    } catch {
      button.textContent = "Copy failed";
    }
    window.setTimeout(() => {
      button.textContent = "Copy";
    }, 1500);
  }

  function wireActions(): void {
    find<HTMLInputElement>("#catalogSearch")?.addEventListener("input", (event) => {
      filter.query = (event.target as HTMLInputElement).value;
      render();
    });
    find<HTMLElement>("#tab-catalog")?.addEventListener("click", (event) => {
      const target = event.target as HTMLElement;
      const kindButton = target.closest<HTMLButtonElement>("[data-catalog-kind]");
      const riskButton = target.closest<HTMLButtonElement>("[data-catalog-risk]");
      const copyButton = target.closest<HTMLButtonElement>("[data-catalog-copy]");
      if (kindButton) {
        filter.kind = kindButton.dataset.catalogKind as CatalogFilter["kind"];
        render();
      } else if (riskButton) {
        filter.risk = riskButton.dataset.catalogRisk as CatalogFilter["risk"];
        render();
      } else if (copyButton) {
        void copyExample(copyButton);
      } else if (target.closest("#catalogExpandAll")) {
        setAllOpen(true);
      } else if (target.closest("#catalogCollapseAll")) {
        setAllOpen(false);
      }
    });
    render();
  }

  return { wireActions };
}
