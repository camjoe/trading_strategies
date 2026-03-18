import { describe, expect, it } from "vitest";

import { renderLogLines } from "../lib/logs";

describe("renderLogLines", () => {
  it("renders empty-state message when no non-empty lines exist", () => {
    const html = renderLogLines(["", "   "]);
    expect(html).toContain("No lines matched this filter");
  });

  it("sanitizes ANSI/BOM artifacts and classifies lines", () => {
    const html = renderLogLines([
      "\uFEFF\u001B[31mERROR broken\u001B[0m",
      "WARN risk",
      "DONE complete",
      "normal",
    ]);

    expect(html).toContain("log-error");
    expect(html).toContain("log-warn");
    expect(html).toContain("log-ok");
    expect(html).toContain("log-plain");
    expect(html).not.toContain("\u001B[31m");
  });

  it("starts collapsible groups on meta lines", () => {
    const html = renderLogLines([
      "RUN META session=1",
      "INFO first",
      "START cycle",
      "FAILED later",
    ]);

    expect(html).toContain("<details class=\"log-group\" open>");
    expect(html).toContain("log-meta-line");
    expect(html).toContain("log-error");
  });
});
