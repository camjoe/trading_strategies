import commandsData from "../assets/commands.json";
import { find, findAll } from "../lib/dom";
import { esc } from "../lib/format";
import { errorMessage, postJson } from "../lib/http";
import type {
  CatalogArgument,
  CatalogData,
  CatalogEntry,
  CatalogFilter,
  CatalogKind,
  CatalogRisk,
  CatalogRunResult,
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

const NOT_RUNNABLE_NOTES: Record<CatalogRisk, string> = {
  "read-only": "This one takes too long for the page. Run it from a terminal with the example above.",
  "writes-local": "This command changes data, so run it from a terminal with the example above.",
  broker: "This command can reach a broker, so run it from a terminal with the example above.",
};

function renderField(argument: CatalogArgument): string {
  const requiredTag = argument.required ? ` <span class="catalog-required">required</span>` : "";
  const label = `<span class="catalog-field-label">${esc(argument.flags.join(" "))}${requiredTag}</span>`;
  const common = `name="${esc(argument.dest)}" title="${esc(argument.help)}"${argument.required ? " required" : ""}`;
  if (argument.kind === "flag") {
    return `<label class="catalog-field catalog-field--flag"><input type="checkbox" ${common} /> ${label}</label>`;
  }
  if (argument.choices) {
    const options = argument.choices.map((choice) => `<option value="${esc(choice)}">${esc(choice)}</option>`).join("");
    return `<label class="catalog-field">${label}<select ${common}><option value=""></option>${options}</select></label>`;
  }
  const inputType = argument.type === "int" || argument.type === "float" ? "number" : "text";
  const step = argument.type === "float" ? ' step="any"' : "";
  const placeholder = formatDefault(argument.default);
  return `<label class="catalog-field">${label}<input type="${inputType}"${step} ${common} placeholder="${esc(placeholder)}" /></label>`;
}

export function renderRunPanel(entry: CatalogEntry): string {
  if (!entry.runnable) {
    return `<p class="catalog-run-note">${esc(NOT_RUNNABLE_NOTES[entry.risk])}</p>`;
  }
  const required = entry.arguments.filter((argument) => argument.required);
  const optional = entry.arguments.filter((argument) => !argument.required);
  const optionalFields = optional.map(renderField).join("");
  const optionalBlock = optional.length
    ? `<details class="catalog-run-optional"><summary>Optional arguments (${optional.length})</summary><div class="catalog-run-fields">${optionalFields}</div></details>`
    : "";
  return `
    <form class="catalog-run" data-catalog-run="${esc(entry.name)}">
      <p class="catalog-run-note">Read-only. This changes no trading data.</p>
      <div class="catalog-run-fields">${required.map(renderField).join("")}</div>
      ${optionalBlock}
      <button type="submit" class="catalog-filter active catalog-run-btn">Run</button>
      <p class="catalog-run-status" role="status" hidden></p>
      <pre class="catalog-run-output" hidden></pre>
    </form>
  `;
}

/** Read a run form into the values the API expects: checked flags as true, filled fields as text. */
export function collectRunValues(form: HTMLFormElement): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const element of Array.from(form.elements)) {
    if (!(element instanceof HTMLInputElement || element instanceof HTMLSelectElement) || !element.name) {
      continue;
    }
    if (element instanceof HTMLInputElement && element.type === "checkbox") {
      if (element.checked) {
        values[element.name] = true;
      }
    } else if (element.value.trim() !== "") {
      values[element.name] = element.value.trim();
    }
  }
  return values;
}

export function describeRunResult(result: CatalogRunResult): { text: string; ok: boolean } {
  if (result.timedOut) {
    return { text: `Stopped: it ran longer than the time limit (${result.durationSeconds}s).`, ok: false };
  }
  const note = result.truncated ? " Output was cut to fit." : "";
  return {
    text: `Exit code ${result.exitCode} in ${result.durationSeconds}s.${note}`,
    ok: result.exitCode === 0,
  };
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
        ${renderRunPanel(entry)}
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

  async function runForm(form: HTMLFormElement): Promise<void> {
    const status = form.querySelector<HTMLElement>(".catalog-run-status");
    const output = form.querySelector<HTMLElement>(".catalog-run-output");
    const button = form.querySelector<HTMLButtonElement>(".catalog-run-btn");
    if (!status || !output || !button) {
      return;
    }
    button.disabled = true;
    status.hidden = false;
    status.className = "catalog-run-status";
    status.textContent = "Running...";
    output.hidden = true;
    try {
      const result = await postJson<CatalogRunResult>("/api/catalog/run", {
        name: form.dataset.catalogRun,
        values: collectRunValues(form),
      });
      const summary = describeRunResult(result);
      status.textContent = summary.text;
      status.classList.add(summary.ok ? "catalog-run-status--ok" : "catalog-run-status--error");
      output.textContent = result.output || "(no output)";
      output.hidden = false;
    } catch (error) {
      status.textContent = errorMessage(error, "The command could not be run.");
      status.classList.add("catalog-run-status--error");
    } finally {
      button.disabled = false;
    }
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
    find<HTMLElement>("#tab-catalog")?.addEventListener("submit", (event) => {
      const form = (event.target as HTMLElement).closest<HTMLFormElement>("[data-catalog-run]");
      if (form) {
        event.preventDefault();
        void runForm(form);
      }
    });
    render();
  }

  return { wireActions };
}
