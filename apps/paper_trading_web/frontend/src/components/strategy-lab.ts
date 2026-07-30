import { esc } from "../lib/format";

export type Trial = {
  candidateIndex: number;
  params: Record<string, unknown>;
  objectiveValue: number | null;
  annualizedReturnPct: number | null;
  maxDrawdownPct: number;
  tradeCount: number;
  eligible: boolean;
  rejectionReason: string | null;
  selected: boolean;
};

export type OptimizationWindow = {
  windowIndex: number;
  trainStart: string;
  trainEnd: string;
  testStart: string;
  testEnd: string;
  oosRunId: number;
  trials: Trial[];
};

export type CompoundedPoint = {
  windowIndex: number;
  testStart: string;
  testEnd: string;
  periodReturnPct: number;
  cumulativeReturnPct: number;
  gapBefore: boolean;
};

export type CompoundedSeries = {
  compoundedReturnPct: number;
  hasGaps: boolean;
  points: CompoundedPoint[];
};

export type Manifest = {
  manifestVersion: string;
  initialCash: number;
  benchmarkTicker: string | null;
  slippageBps: number;
  feePerTrade: number;
  effectiveExecution: Record<string, unknown>;
  tickersFile: string;
  universeSize: number;
  marketDataProvider: string;
  dataAsOf: string;
  engineRevision: string | null;
};

export type ExperimentDetail = {
  experiment: {
    id: number;
    accountName: string;
    primitive: string;
    winnerParams: Record<string, unknown>;
    windowCount: number;
    oosMeanWinnerReturnPct: number | null;
    oosMeanBaselineReturnPct: number | null;
    oosWindowsBeatBaseline: number | null;
    holdoutWinnerReturnPct: number | null;
    holdoutBaselineReturnPct: number | null;
    promotedStrategyId: number | null;
    createdAt: string;
    status: string;
    failureStage: string | null;
    failureMessage: string | null;
    startDate: string;
    endDate: string;
    trainMonths: number;
    testMonths: number;
    stepMonths: number;
    holdoutMonths: number;
    warmupMonths: number;
    candidateBudget: number;
    holdoutRunId: number | null;
  };
  gate: { passed: boolean; reasons: string[] };
  windows: OptimizationWindow[];
  compoundedOos: CompoundedSeries | null;
  manifest: Manifest | null;
};

const NA = "n/a";

function num(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined ? NA : value.toFixed(digits);
}

/** Training months the optimizer defaults to when the form does not send one.
 * Mirrors `RunOptimizationRequest.trainMonths`; only ever used to *estimate*
 * the window count before submitting. */
const DEFAULT_TRAIN_MONTHS = 12;

/** Test/step months the optimizer defaults to — one window per month. */
const DEFAULT_STEP_MONTHS = 1;

/** Warn past this many simulations. One measured ~0.74s on the default
 * 12-ticker universe, so ~200 is about the point where a synchronous run stops
 * feeling like a request and starts being a wait. */
export const SWEEP_WARNING_SIMULATIONS = 200;

export type SweepEstimate = {
  candidates: number;
  windows: number;
  simulations: number;
  overWarningThreshold: boolean;
};

/** Estimate the real size of a sweep before it is submitted.
 *
 * The cost that matters is `candidates x windows`, not the candidate count on
 * its own — a modest grid over two years of monthly windows is still an hour of
 * work. Each window also runs a persisted out-of-sample run and a metrics-only
 * baseline, and the holdout runs the same pair once, which is the `2 * windows + 2`.
 *
 * An estimate, not a contract: the server owns the real window geometry. */
export function estimateSweep(input: {
  candidates: number;
  lookbackMonths: number;
  holdoutMonths: number;
}): SweepEstimate {
  const searchMonths = input.lookbackMonths - input.holdoutMonths - DEFAULT_TRAIN_MONTHS;
  const windows = Math.max(0, Math.floor(searchMonths / DEFAULT_STEP_MONTHS));
  const simulations = windows === 0 ? 0 : input.candidates * windows + 2 * windows + 2;
  return {
    candidates: input.candidates,
    windows,
    simulations,
    overWarningThreshold: simulations > SWEEP_WARNING_SIMULATIONS,
  };
}

/** The confirm-dialog text for a sweep, stating what the run will actually cost. */
export function sweepConfirmMessage(estimate: SweepEstimate): string {
  if (estimate.windows === 0)
    return "This lookback leaves no room for a training window after the holdout. Submit anyway?";
  const summary =
    `Run ${estimate.candidates} candidates over ${estimate.windows} windows ` +
    `— about ${estimate.simulations} backtests.`;
  return estimate.overWarningThreshold
    ? `${summary} That is a long synchronous run; the page stays open until it finishes. Continue?`
    : `${summary} Continue?`;
}

/** Best objective first, with every rejected candidate kept visible below it.
 *
 * The rejected set is the multiple-testing record — how many parameter
 * combinations were tried before one was selected — so it is ordered, not hidden. */
export function rankedTrials(trials: Trial[]): Trial[] {
  return [...trials].sort((left, right) => {
    if (left.eligible !== right.eligible) return left.eligible ? -1 : 1;
    return (
      (right.objectiveValue ?? -Infinity) - (left.objectiveValue ?? -Infinity)
    );
  });
}

export function renderTrialsTable(trials: Trial[]): string {
  if (!trials.length)
    return '<p class="admin-note">No candidate trials persisted for this window.</p>';
  const rows = rankedTrials(trials)
    .map((trial, index) => {
      const status = trial.selected
        ? "winner"
        : trial.eligible
          ? "eligible"
          : esc(trial.rejectionReason ?? "rejected");
      const pill = trial.selected
        ? "ok"
        : trial.eligible
          ? "warning"
          : "missing";
      return `<tr>
        <td>${index + 1}</td>
        <td><code>${esc(JSON.stringify(trial.params))}</code></td>
        <td>${num(trial.objectiveValue, 4)}</td>
        <td>${num(trial.annualizedReturnPct)}</td>
        <td>${num(trial.maxDrawdownPct)}</td>
        <td>${trial.tradeCount}</td>
        <td><span class="status-pill ${pill}">${status}</span></td>
      </tr>`;
    })
    .join("");
  return `<table><thead><tr><th>Rank</th><th>Params</th><th>Objective</th><th>Ann. return %</th><th>Max DD %</th><th>Trades</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderWindows(windows: OptimizationWindow[]): string {
  if (!windows.length) {
    return '<p class="admin-note">No per-window audit persisted (experiment predates the window audit).</p>';
  }
  return windows
    .map(window => {
      const eligible = window.trials.filter(trial => trial.eligible).length;
      return `<details>
        <summary>Window ${window.windowIndex} · train ${esc(window.trainStart)}..${esc(window.trainEnd)} · test ${esc(window.testStart)}..${esc(window.testEnd)} · OOS run #${window.oosRunId} · ${eligible}/${window.trials.length} eligible</summary>
        ${renderTrialsTable(window.trials)}
      </details>`;
    })
    .join("");
}

function renderCompounded(series: CompoundedSeries | null): string {
  if (!series)
    return '<p class="admin-note">Compounded out-of-sample series unavailable.</p>';
  const gaps = series.hasGaps
    ? ' <span class="status-pill warning">has gaps</span>'
    : "";
  const points = series.points
    .map(
      point => `<tr>
      <td>${point.windowIndex}</td><td>${esc(point.testStart)}..${esc(point.testEnd)}</td>
      <td>${num(point.periodReturnPct)}</td><td>${num(point.cumulativeReturnPct)}</td>
      <td>${point.gapBefore ? "gap" : ""}</td></tr>`,
    )
    .join("");
  return `<p>Compounded OOS return: <strong>${num(series.compoundedReturnPct)}%</strong>${gaps}</p>
    <details><summary>${series.points.length} compounded windows</summary>
      <table><thead><tr><th>#</th><th>Test window</th><th>Period %</th><th>Cumulative %</th><th></th></tr></thead><tbody>${points}</tbody></table>
    </details>`;
}

function renderManifest(manifest: Manifest | null): string {
  if (!manifest)
    return '<p class="admin-note">No provenance manifest stored for this run.</p>';
  return `<details><summary>Run provenance (${esc(manifest.manifestVersion)})</summary>
    <p class="admin-note">Universe ${manifest.universeSize} tickers from ${esc(manifest.tickersFile)} · provider ${esc(manifest.marketDataProvider)} · as of ${esc(manifest.dataAsOf)}</p>
    <p class="admin-note">Economics: slippage ${num(manifest.slippageBps)} bps · fee ${num(manifest.feePerTrade)} · initial cash ${num(manifest.initialCash)} · benchmark ${esc(manifest.benchmarkTicker ?? NA)}</p>
    <p class="admin-note">Engine revision: ${esc(manifest.engineRevision ?? NA)}</p>
    <pre>${esc(JSON.stringify(manifest.effectiveExecution, null, 2))}</pre>
  </details>`;
}

export function renderOptimizationDetail(detail: ExperimentDetail): string {
  const item = detail.experiment;

  if (item.status === "failed") {
    return `<section class="config-summary-card">
      <div class="ops-card-head"><strong>Experiment #${item.id}</strong><span class="status-pill missing">failed</span></div>
      <p class="admin-note">${esc(item.accountName)} · ${esc(item.primitive)}</p>
      <p>Failed during <strong>${esc(item.failureStage ?? "unknown stage")}</strong> after ${item.windowCount} window(s).</p>
      <pre>${esc(item.failureMessage ?? "No failure message recorded.")}</pre>
    </section>`;
  }

  const gate = detail.gate.passed
    ? '<span class="status-pill ok">gate: PASS</span>'
    : `<span class="status-pill missing">gate: FAIL</span><ul>${detail.gate.reasons.map(reason => `<li>${esc(reason)}</li>`).join("")}</ul>`;

  return `<section class="config-summary-card">
    <div class="ops-card-head"><strong>Experiment #${item.id}</strong><span class="status-pill ${item.promotedStrategyId ? "ok" : "warning"}">${item.promotedStrategyId ? "promoted" : "not promoted"}</span></div>
    <p class="admin-note">${esc(item.accountName)} · ${esc(item.primitive)} · ${esc(item.startDate)}..${esc(item.endDate)} · created ${esc(item.createdAt)}</p>
    <p class="admin-note">Windows ${item.windowCount} · train/test/step/holdout(mo) ${item.trainMonths}/${item.testMonths}/${item.stepMonths}/${item.holdoutMonths} · warmup ${item.warmupMonths} · budget ${item.candidateBudget}</p>
    <p>Winner params:</p><pre>${esc(JSON.stringify(item.winnerParams, null, 2))}</pre>
    <p>OOS mean winner/default: <strong>${num(item.oosMeanWinnerReturnPct)}%</strong> / ${num(item.oosMeanBaselineReturnPct)}% · beat default in ${item.oosWindowsBeatBaseline ?? NA}/${item.windowCount} windows</p>
    <p>Holdout${item.holdoutRunId === null ? "" : ` (run #${item.holdoutRunId})`} winner/default: <strong>${num(item.holdoutWinnerReturnPct)}%</strong> / ${num(item.holdoutBaselineReturnPct)}%</p>
    <div>${gate}</div>
  </section>
  <section class="config-summary-card"><h3>Compounded out-of-sample</h3>${renderCompounded(detail.compoundedOos)}</section>
  <section class="config-summary-card"><h3>Windows and evaluated candidates</h3>${renderWindows(detail.windows)}</section>
  <section class="config-summary-card"><h3>Provenance</h3>${renderManifest(detail.manifest)}</section>`;
}
