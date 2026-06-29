interface BacktestBasePayload {
  account: string;
  tickersFile: string;
  universeHistoryDir: string | null;
  start: string | null;
  end: string | null;
  lookbackMonths: number | null;
  allowApproximateLeaps: boolean;
}

interface BacktestRunPayload extends BacktestBasePayload {
  slippageBps: number;
  fee: number;
  runName: string | null;
}

interface WalkForwardPayload extends BacktestBasePayload {
  testMonths: number;
  stepMonths: number;
  slippageBps: number;
  fee: number;
  runNamePrefix: string | null;
}

function parseOptInt(raw: string): number | null {
  const value = raw.trim();
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : null;
}

function parseOptStr(raw: string): string | null {
  const value = raw.trim();
  return value ? value : null;
}

function parseFormNumber(fd: FormData, key: string, fallback: number): number {
  const raw = String(fd.get(key) ?? "").trim();
  if (!raw) {
    return fallback;
  }
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function buildBacktestBasePayload(fd: FormData): BacktestBasePayload {
  return {
    account: String(fd.get("account") ?? "").trim(),
    tickersFile: String(fd.get("tickersFile") ?? "trading/config/trade_universe.txt").trim(),
    universeHistoryDir: parseOptStr(String(fd.get("universeHistoryDir") ?? "")),
    start: parseOptStr(String(fd.get("start") ?? "")),
    end: parseOptStr(String(fd.get("end") ?? "")),
    lookbackMonths: parseOptInt(String(fd.get("lookbackMonths") ?? "")),
    allowApproximateLeaps: fd.get("allowApproximateLeaps") !== null,
  };
}

export function buildBacktestRunPayload(form: HTMLFormElement): BacktestRunPayload {
  const fd = new FormData(form);
  return {
    ...buildBacktestBasePayload(fd),
    slippageBps: parseFormNumber(fd, "slippageBps", 5),
    fee: parseFormNumber(fd, "fee", 0),
    runName: parseOptStr(String(fd.get("runName") ?? "")),
  };
}

export function buildWalkForwardPayload(form: HTMLFormElement): WalkForwardPayload {
  const fd = new FormData(form);
  return {
    ...buildBacktestBasePayload(fd),
    testMonths: parseFormNumber(fd, "testMonths", 1),
    stepMonths: parseFormNumber(fd, "stepMonths", 1),
    slippageBps: parseFormNumber(fd, "slippageBps", 5),
    fee: parseFormNumber(fd, "fee", 0),
    runNamePrefix: parseOptStr(String(fd.get("runNamePrefix") ?? "")),
  };
}

export function validateDateInputs(start: string | null, lookbackMonths: number | null): string | null {
  if (start && lookbackMonths !== null) {
    return "Use either Start date or Lookback months, not both.";
  }
  return null;
}
