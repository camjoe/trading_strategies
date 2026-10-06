import { esc } from "../lib/format";
import { errorMessage, postJson } from "../lib/http";
import type { CatalogEntry, CatalogRunResult } from "../types/catalog";

export const CHECKS_GROUP = "Quality Checks";

const TERMINAL_ART_SVG = `
  <svg class="catalog-showcase-art" viewBox="0 0 120 72" aria-hidden="true">
    <rect x="4" y="4" width="112" height="64" rx="6" />
    <line x1="4" y1="16" x2="116" y2="16" />
    <path class="catalog-showcase-art-tick" d="M14 30 l4 4 l7 -8" />
    <line x1="32" y1="30" x2="84" y2="30" />
    <path class="catalog-showcase-art-tick" d="M14 44 l4 4 l7 -8" />
    <line x1="32" y1="44" x2="96" y2="44" />
    <line class="catalog-showcase-art-cursor" x1="14" y1="58" x2="22" y2="58" />
  </svg>`;

function renderLine(name: string): string {
  return `
    <li class="check-line check-line--pending" data-check-line="${esc(name)}">
      <details>
        <summary>
          <span class="check-line-icon" aria-hidden="true"></span>
          <code class="check-line-name">${esc(name)}</code>
          <span class="check-line-summary">waiting</span>
          <span class="check-line-time"></span>
        </summary>
        <pre class="check-line-output"></pre>
      </details>
    </li>`;
}

/** The checks card: every runnable entry in the group, run one at a time. */
export function renderCheckRunner(entries: CatalogEntry[]): string {
  const names = entries.filter((entry) => entry.runnable).map((entry) => entry.name);
  if (!names.length) {
    return "";
  }
  return `
  <div class="catalog-showcase" data-showcase="check-runner">
    <div class="catalog-showcase-head">
      ${TERMINAL_ART_SVG}
      <div class="catalog-showcase-text">
        <p class="catalog-showcase-kicker">Live</p>
        <h5 class="catalog-showcase-title">Repository checks</h5>
        <p class="catalog-showcase-copy">
          Run the ${names.length} fast read-only checks on the backend, one after another: docs drift, layer
          boundaries, live-trading safety, secrets, migrations, and more.
        </p>
        <p class="catalog-showcase-meta" data-check-status hidden></p>
      </div>
      <div class="catalog-showcase-actions">
        <button type="button" class="catalog-filter active" data-check-run>Run checks</button>
      </div>
    </div>
    <ol class="check-terminal" data-check-terminal hidden>${names.map(renderLine).join("")}</ol>
  </div>`;
}

/** The last non-empty output line, which is where every check prints its verdict. */
export function verdictLine(output: string): string {
  const lines = output.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const last = lines.at(-1) ?? "(no output)";
  return last.length > 140 ? `${last.slice(0, 139)}…` : last;
}

function setText(line: HTMLElement, selector: string, text: string): void {
  const element = line.querySelector(selector);
  if (element) {
    element.textContent = text;
  }
}

type CheckOutcome = "pass" | "warn" | "fail";

/** A check that exits 0 but prints a WARN line passed with a warning. */
export function checkOutcome(result: CatalogRunResult): CheckOutcome {
  if (result.exitCode !== 0 || result.timedOut) {
    return "fail";
  }
  return /^\s*WARN\b/m.test(result.output) ? "warn" : "pass";
}

function setLineState(line: HTMLElement, state: "pending" | "running" | CheckOutcome): void {
  line.className = `check-line check-line--${state}`;
}

function resetLine(line: HTMLElement): void {
  setLineState(line, "pending");
  line.querySelector("details")?.removeAttribute("open");
  setText(line, ".check-line-summary", "waiting");
  setText(line, ".check-line-time", "");
  setText(line, ".check-line-output", "");
}

async function runChecks(card: HTMLElement, button: HTMLButtonElement): Promise<void> {
  const terminal = card.querySelector<HTMLElement>("[data-check-terminal]");
  const status = card.querySelector<HTMLElement>("[data-check-status]");
  if (!terminal || !status) {
    return;
  }
  const lines = Array.from(terminal.querySelectorAll<HTMLElement>("[data-check-line]"));
  lines.forEach(resetLine);
  terminal.hidden = false;
  button.disabled = true;
  button.textContent = "Running...";
  status.hidden = false;
  status.className = "catalog-showcase-meta";
  status.textContent = `Running ${lines.length} checks...`;

  const started = performance.now();
  const counts: Record<CheckOutcome, number> = { pass: 0, warn: 0, fail: 0 };
  for (const line of lines) {
    const name = line.dataset.checkLine ?? "";
    setLineState(line, "running");
    setText(line, ".check-line-summary", "running");
    let result: CatalogRunResult;
    try {
      result = await postJson<CatalogRunResult>("/api/catalog/run", { name, values: {} });
    } catch (error) {
      const message = errorMessage(error, "The request failed.");
      const hint = error instanceof TypeError ? " Is the backend running? Start it with python -m scripts.launch_ui." : "";
      setLineState(line, "fail");
      setText(line, ".check-line-summary", message);
      status.textContent = `Stopped at ${name}: ${message}.${hint}`;
      status.classList.add("check-status--error");
      button.disabled = false;
      button.textContent = "Run again";
      return;
    }
    const outcome = checkOutcome(result);
    counts[outcome] += 1;
    setLineState(line, outcome);
    const summary = result.timedOut ? "stopped: over the time limit" : verdictLine(result.output);
    setText(line, ".check-line-summary", summary);
    setText(line, ".check-line-time", `${result.durationSeconds.toFixed(1)}s`);
    setText(line, ".check-line-output", result.output || "(no output)");
  }

  const seconds = ((performance.now() - started) / 1000).toFixed(1);
  const warnings = counts.warn ? ` · ${counts.warn} with warnings` : "";
  status.textContent = `${counts.pass} passed${warnings} · ${counts.fail} failed in ${seconds}s`;
  status.classList.add(counts.fail ? "check-status--error" : "check-status--ok");
  button.disabled = false;
  button.textContent = "Run again";
}

export function handleCheckRunnerClick(target: HTMLElement): boolean {
  const button = target.closest<HTMLButtonElement>("[data-check-run]");
  const card = button?.closest<HTMLElement>('[data-showcase="check-runner"]');
  if (!button || !card || button.disabled) {
    return false;
  }
  void runChecks(card, button);
  return true;
}
