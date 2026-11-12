import ciData from "../assets/ci.json";
import { esc } from "../lib/format";
import type { CiJob, CiPipeline, CiStep, CiTrigger } from "../types/ci";

const PIPELINE_ART_SVG = `
  <svg class="catalog-showcase-art" viewBox="0 0 120 72" aria-hidden="true">
    <circle cx="12" cy="36" r="7" />
    <rect x="34" y="27" width="22" height="18" rx="4" />
    <rect x="80" y="6" width="30" height="16" rx="4" />
    <rect x="80" y="28" width="30" height="16" rx="4" />
    <rect x="80" y="50" width="30" height="16" rx="4" />
    <path class="catalog-showcase-art-link" d="M19 36 H34 M56 36 C 68 36, 68 14, 80 14 M56 36 H80 M56 36 C 68 36, 68 58, 80 58" />
  </svg>`;

/** `python_related` reads as "python". */
export function filterLabel(name: string): string {
  return name.replace(/_related$/, "").replaceAll("_", " ");
}

export function describeTrigger(trigger: CiTrigger): string {
  const event = trigger.event.replaceAll("_", " ");
  return trigger.branches.length ? `${event} to ${trigger.branches.join(", ")}` : `every ${event}`;
}

/** When a job runs, in words, from its parsed `if:` condition. */
export function describeWhen(job: CiJob): string {
  if (!job.when_changed.length) {
    return job.condition ? `When: ${job.condition}` : "Every run";
  }
  const areas = job.when_changed.map(filterLabel).join(" or ");
  return job.always_on_push
    ? `Every push; on a pull request, only when ${areas} files change`
    : `Only when ${areas} files change`;
}

/** Jobs grouped into stages by `needs` depth; a job runs after every job in earlier stages it needs. */
export function pipelineStages(jobs: CiJob[]): CiJob[][] {
  const depth = new Map<string, number>();
  const byId = new Map(jobs.map((job) => [job.id, job]));
  const depthOf = (job: CiJob, seen: Set<string>): number => {
    const known = depth.get(job.id);
    if (known !== undefined) {
      return known;
    }
    if (seen.has(job.id)) {
      return 0;
    }
    seen.add(job.id);
    const parents = job.needs.map((id) => byId.get(id)).filter((parent): parent is CiJob => Boolean(parent));
    const value = parents.length ? Math.max(...parents.map((parent) => depthOf(parent, seen))) + 1 : 0;
    depth.set(job.id, value);
    return value;
  };
  const stages: CiJob[][] = [];
  for (const job of jobs) {
    const index = depthOf(job, new Set());
    (stages[index] ??= []).push(job);
  }
  return stages.filter(Boolean);
}

function renderStep(step: CiStep): string {
  if (step.run) {
    const lines = step.run.split("\n").map((line) => `<code>${esc(line)}</code>`).join("");
    return `<li class="ci-step ci-step--run"><span class="ci-step-name">${esc(step.name)}</span>${lines}</li>`;
  }
  return `<li class="ci-step"><span class="ci-step-name">${esc(step.name)}</span></li>`;
}

function renderFilters(job: CiJob): string {
  const names = Object.entries(job.path_filters);
  if (!names.length) {
    return "";
  }
  const chips = names
    .map(([name, globs]) => `<span class="ci-filter" title="${esc(globs.join("\n"))}">${esc(filterLabel(name))}</span>`)
    .join("");
  return `<div class="ci-filters"><span class="ci-filters-label">Sorts changed files into</span>${chips}</div>`;
}

function renderJob(job: CiJob): string {
  return `
    <article class="ci-job" data-ci-job="${esc(job.id)}">
      <header class="ci-job-head">
        <span class="ci-job-name">${esc(job.name)}</span>
        ${job.runs_on ? `<span class="ci-job-runner">${esc(job.runs_on)}</span>` : ""}
      </header>
      <p class="ci-job-when">${esc(describeWhen(job))}</p>
      ${renderFilters(job)}
      <ol class="ci-steps" data-ci-steps hidden>${job.steps.map(renderStep).join("")}</ol>
    </article>`;
}

export function renderPipeline(pipeline: CiPipeline): string {
  const triggers = pipeline.triggers
    .map((trigger) => `<li class="ci-trigger">${esc(describeTrigger(trigger))}</li>`)
    .join("");
  const stages = pipelineStages(pipeline.jobs)
    .map((stage) => `<div class="ci-stage">${stage.map(renderJob).join("")}</div>`)
    .join(`<span class="ci-arrow" aria-hidden="true"></span>`);
  return `
  <div class="catalog-showcase" data-showcase="ci-pipeline">
    <div class="catalog-showcase-head">
      ${PIPELINE_ART_SVG}
      <div class="catalog-showcase-text">
        <p class="catalog-showcase-kicker">From ${esc(pipeline.file)}</p>
        <h5 class="catalog-showcase-title">${esc(pipeline.name)} pipeline</h5>
        <p class="catalog-showcase-copy">
          What GitHub Actions runs for this repository. A first job sorts the changed files, then each gate runs
          only when its area changed.
        </p>
      </div>
      <div class="catalog-showcase-actions">
        <button type="button" class="catalog-filter" data-ci-steps-toggle aria-expanded="false">Show steps</button>
      </div>
    </div>
    <div class="ci-pipeline">
      <div class="ci-stage ci-stage--trigger">
        <span class="ci-stage-label">Triggers</span>
        <ul class="ci-triggers">${triggers}</ul>
      </div>
      <span class="ci-arrow" aria-hidden="true"></span>
      ${stages}
    </div>
  </div>`;
}

export function renderCiPipeline(): string {
  return renderPipeline(ciData as CiPipeline);
}

export function handleCiPipelineClick(target: HTMLElement): boolean {
  const toggle = target.closest<HTMLButtonElement>("[data-ci-steps-toggle]");
  const card = toggle?.closest<HTMLElement>('[data-showcase="ci-pipeline"]');
  if (!toggle || !card) {
    return false;
  }
  const show = toggle.getAttribute("aria-expanded") !== "true";
  card.querySelectorAll<HTMLElement>("[data-ci-steps]").forEach((steps) => {
    steps.hidden = !show;
  });
  toggle.setAttribute("aria-expanded", String(show));
  toggle.textContent = show ? "Hide steps" : "Show steps";
  return true;
}
