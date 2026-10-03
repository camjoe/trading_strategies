// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  collectRunValues,
  createCatalogFeature,
  describeRunResult,
  renderRunPanel,
} from "../../features/catalog";
import catalogTemplate from "../../views/catalog.html?raw";
import type { CatalogArgument, CatalogData, CatalogEntry, CatalogRunResult } from "../../types/catalog";

function argument(overrides: Partial<CatalogArgument>): CatalogArgument {
  return {
    flags: ["--x"],
    dest: "x",
    positional: false,
    kind: "value",
    type: "str",
    required: false,
    default: null,
    choices: null,
    help: "",
    ...overrides,
  };
}

function runnableEntry(overrides: Partial<CatalogEntry> = {}): CatalogEntry {
  return {
    name: "report",
    kind: "cli",
    group: "Reporting",
    risk: "read-only",
    module: null,
    schedule: null,
    runnable: true,
    help: "Show account status.",
    example: "python -m app report --account <ACCOUNT>",
    arguments: [
      argument({ flags: ["--account"], dest: "account", required: true, help: "Account name" }),
      argument({ flags: ["--limit"], dest: "limit", type: "int", default: 20, help: "Rows" }),
      argument({ flags: ["--format"], dest: "format", default: "text", choices: ["text", "json"] }),
      argument({ flags: ["--verbose"], dest: "verbose", kind: "flag", type: "flag", default: false }),
    ],
    ...overrides,
  };
}

function resultOf(overrides: Partial<CatalogRunResult> = {}): CatalogRunResult {
  return {
    name: "report",
    command: "python -m x",
    exitCode: 0,
    timedOut: false,
    truncated: false,
    durationSeconds: 1.5,
    output: "",
    ...overrides,
  };
}

describe("renderRunPanel", () => {
  it("explains why an entry that is not runnable has no button", () => {
    const base = runnableEntry({ runnable: false });

    expect(renderRunPanel({ ...base, risk: "writes-local" })).toContain("changes data");
    expect(renderRunPanel({ ...base, risk: "broker" })).toContain("can reach a broker");
    expect(renderRunPanel({ ...base, risk: "read-only" })).toContain("takes too long");
    expect(renderRunPanel({ ...base, risk: "broker" })).not.toContain("<form");
  });

  it("renders a form with the right control for each argument type", () => {
    document.body.innerHTML = renderRunPanel(runnableEntry());

    expect(document.querySelector("form[data-catalog-run='report']")).not.toBeNull();
    expect(document.querySelector<HTMLInputElement>("input[name='account']")?.required).toBe(true);
    expect(document.querySelector<HTMLInputElement>("input[name='limit']")?.type).toBe("number");
    expect(document.querySelector<HTMLInputElement>("input[name='limit']")?.placeholder).toBe("20");
    expect(document.querySelectorAll("select[name='format'] option")).toHaveLength(3);
    expect(document.querySelector<HTMLInputElement>("input[name='verbose']")?.type).toBe("checkbox");
  });

  it("keeps optional arguments in a collapsed group", () => {
    document.body.innerHTML = renderRunPanel(runnableEntry());

    const optional = document.querySelector(".catalog-run-optional");
    expect(optional?.querySelector("summary")?.textContent).toContain("Optional arguments (3)");
    expect(optional?.querySelector("input[name='account']")).toBeNull();
  });

  it("omits the optional group when every argument is required", () => {
    const entry = runnableEntry();
    document.body.innerHTML = renderRunPanel({ ...entry, arguments: entry.arguments.slice(0, 1) });

    expect(document.querySelector(".catalog-run-optional")).toBeNull();
  });

  it("escapes markup in argument names and help", () => {
    const entry = runnableEntry({
      arguments: [argument({ dest: "a", flags: ["--a"], help: '"><script>x</script>', required: true })],
    });
    document.body.innerHTML = renderRunPanel(entry);

    expect(document.querySelector("script")).toBeNull();
  });
});

describe("collectRunValues", () => {
  function formWith(entry: CatalogEntry): HTMLFormElement {
    document.body.innerHTML = renderRunPanel(entry);
    return document.querySelector<HTMLFormElement>("form") as HTMLFormElement;
  }

  it("returns filled fields as trimmed text and checked flags as true", () => {
    const form = formWith(runnableEntry());
    (form.elements.namedItem("account") as HTMLInputElement).value = "  alpha ";
    (form.elements.namedItem("limit") as HTMLInputElement).value = "5";
    (form.elements.namedItem("format") as HTMLSelectElement).value = "json";
    (form.elements.namedItem("verbose") as HTMLInputElement).checked = true;

    expect(collectRunValues(form)).toEqual({ account: "alpha", limit: "5", format: "json", verbose: true });
  });

  it("leaves out empty fields and unchecked flags", () => {
    const form = formWith(runnableEntry());
    (form.elements.namedItem("account") as HTMLInputElement).value = "alpha";

    expect(collectRunValues(form)).toEqual({ account: "alpha" });
  });
});

describe("describeRunResult", () => {
  it("reports success, failure, truncation, and timeout", () => {
    expect(describeRunResult(resultOf())).toEqual({ text: "Exit code 0 in 1.5s.", ok: true });
    expect(describeRunResult(resultOf({ exitCode: 2 })).ok).toBe(false);
    expect(describeRunResult(resultOf({ truncated: true })).text).toContain("Output was cut");
    expect(describeRunResult(resultOf({ timedOut: true, exitCode: null }))).toEqual({
      text: "Stopped: it ran longer than the time limit (1.5s).",
      ok: false,
    });
  });
});

describe("running a command from the page", () => {
  function renderRunnable(): HTMLFormElement {
    document.body.innerHTML = catalogTemplate;
    const data: CatalogData = {
      schema_version: 2,
      cli_invocation: "python -m app",
      groups: [{ name: "Reporting", kind: "cli" }],
      commands: [runnableEntry()],
    };
    createCatalogFeature(data).wireActions();
    const form = document.querySelector<HTMLFormElement>("form[data-catalog-run]") as HTMLFormElement;
    (form.elements.namedItem("account") as HTMLInputElement).value = "alpha";
    return form;
  }

  function statusOf(form: HTMLFormElement): HTMLElement {
    return form.querySelector<HTMLElement>(".catalog-run-status") as HTMLElement;
  }

  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts the name and values, then shows the output and exit code", async () => {
    const body = resultOf({ durationSeconds: 0.4, output: "hello" });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, text: async () => JSON.stringify(body) });
    vi.stubGlobal("fetch", fetchMock);
    const form = renderRunnable();

    form.requestSubmit();
    await vi.waitFor(() => expect(statusOf(form).textContent).toContain("Exit code 0"));

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url).endsWith("/api/catalog/run")).toBe(true);
    expect(JSON.parse(init.body)).toEqual({ name: "report", values: { account: "alpha" } });
    expect(form.querySelector(".catalog-run-output")?.textContent).toBe("hello");
    expect(statusOf(form).classList.contains("catalog-run-status--ok")).toBe(true);
    expect((form.querySelector(".catalog-run-btn") as HTMLButtonElement).disabled).toBe(false);
  });

  it("shows an error when the backend cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Failed to fetch")));
    const form = renderRunnable();

    form.requestSubmit();
    await vi.waitFor(() => expect(statusOf(form).textContent).toBe("Failed to fetch"));

    expect(statusOf(form).classList.contains("catalog-run-status--error")).toBe(true);
    expect(form.querySelector<HTMLElement>(".catalog-run-output")?.hidden).toBe(true);
  });

  it("shows the reason the server gave when it refuses a run", async () => {
    const refusal = { ok: false, status: 400, json: async () => ({ detail: "account is required" }) };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(refusal));
    const form = renderRunnable();

    form.requestSubmit();
    await vi.waitFor(() => expect(statusOf(form).textContent).toContain("account is required"));
  });

  it("does not submit a form that is missing a required value", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const form = renderRunnable();
    (form.elements.namedItem("account") as HTMLInputElement).value = "";

    form.requestSubmit();

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
