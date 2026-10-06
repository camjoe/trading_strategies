// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { checkOutcome, handleCheckRunnerClick, renderCheckRunner, verdictLine } from "../../features/catalog-check-runner";
import type { CatalogEntry, CatalogRunResult } from "../../types/catalog";

function check(name: string, runnable = true): CatalogEntry {
  return {
    name,
    kind: "tool",
    group: "Quality Checks",
    family: null,
    risk: "read-only",
    module: null,
    schedule: null,
    runnable,
    help: "Help.",
    example: `python -m ${name}`,
    arguments: [],
  };
}

function result(name: string, overrides: Partial<CatalogRunResult> = {}): CatalogRunResult {
  return {
    name,
    command: `python -m ${name}`,
    exitCode: 0,
    timedOut: false,
    truncated: false,
    durationSeconds: 1.25,
    output: `starting\nPASS: ${name} ok\n`,
    ...overrides,
  };
}

function respondWith(results: CatalogRunResult[]): ReturnType<typeof vi.fn> {
  const queue = [...results];
  return vi.fn().mockImplementation(async () => ({ ok: true, text: async () => JSON.stringify(queue.shift()) }));
}

describe("renderCheckRunner", () => {
  it("lists only the runnable entries, in order", () => {
    const html = renderCheckRunner([check("layer-check"), check("pytest-check", false), check("link-check")]);

    expect(html.match(/data-check-line="/g)).toHaveLength(2);
    expect(html.indexOf("layer-check")).toBeLessThan(html.indexOf("link-check"));
    expect(html).not.toContain("pytest-check");
    expect(html).toContain("Run the 2 fast read-only checks");
  });

  it("renders nothing when no entry can run", () => {
    expect(renderCheckRunner([check("pytest-check", false)])).toBe("");
  });
});

describe("verdictLine", () => {
  it("returns the last non-empty line, shortened when long", () => {
    expect(verdictLine("a\nPASS: done\n\n")).toBe("PASS: done");
    expect(verdictLine("")).toBe("(no output)");
    expect(verdictLine("x".repeat(200))).toHaveLength(140);
  });
});

describe("checkOutcome", () => {
  it("fails on a non-zero exit or a timeout, warns on a WARN line, and passes otherwise", () => {
    expect(checkOutcome(result("a"))).toBe("pass");
    expect(checkOutcome(result("a", { output: "starting\nWARN: advisory issues\n" }))).toBe("warn");
    expect(checkOutcome(result("a", { output: "no WARNINGS here\n" }))).toBe("pass");
    expect(checkOutcome(result("a", { exitCode: 1 }))).toBe("fail");
    expect(checkOutcome(result("a", { timedOut: true, exitCode: null }))).toBe("fail");
  });
});

describe("running the checks", () => {
  const card = () => document.querySelector<HTMLElement>('[data-showcase="check-runner"]') as HTMLElement;
  const runButton = () => card().querySelector<HTMLButtonElement>("[data-check-run]") as HTMLButtonElement;
  const status = () => card().querySelector<HTMLElement>("[data-check-status]")?.textContent ?? "";
  const lineClass = (name: string) => card().querySelector(`[data-check-line="${name}"]`)?.className ?? "";

  beforeEach(() => {
    document.body.innerHTML = renderCheckRunner([check("layer-check"), check("link-check")]);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("runs each check in order and marks it passed or failed", async () => {
    const fetchMock = respondWith([
      result("layer-check", { output: "WARN: one advisory issue" }),
      result("link-check", { exitCode: 1, output: "FAIL: 2 broken links" }),
    ]);
    vi.stubGlobal("fetch", fetchMock);

    expect(handleCheckRunnerClick(runButton())).toBe(true);
    await vi.waitFor(() => expect(status()).toMatch(/^0 passed · 1 with warnings · 1 failed in/));

    expect(fetchMock.mock.calls.map((call) => JSON.parse(call[1].body).name)).toEqual(["layer-check", "link-check"]);
    expect(lineClass("layer-check")).toContain("check-line--warn");
    expect(lineClass("link-check")).toContain("check-line--fail");
    expect(card().querySelector('[data-check-line="link-check"] .check-line-summary')?.textContent).toBe(
      "FAIL: 2 broken links",
    );
    expect(runButton().textContent).toBe("Run again");
  });

  it("stops at the first request the backend does not answer", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetchMock);

    handleCheckRunnerClick(runButton());
    await vi.waitFor(() => expect(status()).toContain("Stopped at layer-check: Failed to fetch."));
    expect(status()).toContain("Is the backend running?");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(lineClass("layer-check")).toContain("check-line--fail");
    expect(lineClass("link-check")).toContain("check-line--pending");
    expect(runButton().disabled).toBe(false);
  });
});
