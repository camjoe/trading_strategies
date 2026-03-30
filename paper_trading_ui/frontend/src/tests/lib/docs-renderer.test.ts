import { describe, expect, it } from "vitest";

import { buildDocsTemplate } from "../../lib/docs-renderer";

// buildDocsTemplate() is the single public entry point. Calling it exercises
// all internal builders (buildFinanceCard, buildSoftwareCard, buildApiCard,
// buildPackagesSection, buildApiSection, buildFinanceSection, esc, etc.).

describe("buildDocsTemplate", () => {
  let html: string;

  // Build once and share across all assertions — the function is pure.
  html = buildDocsTemplate();

  it("returns a non-empty string wrapped in the docs tab panel", () => {
    expect(typeof html).toBe("string");
    expect(html.length).toBeGreaterThan(0);
    expect(html).toContain('id="tab-docs"');
  });

  // ---------------------------------------------------------------------------
  // Finance card
  // ---------------------------------------------------------------------------

  it("includes the Finance card heading", () => {
    expect(html).toContain("Financial &amp; Market Knowledge");
  });

  it("renders at least one finance section with a table", () => {
    // Every finance section has a ref-table inside a ref-section.
    expect(html).toContain("ref-section");
    expect(html).toContain("ref-table");
  });

  it("applies the DTE term label override", () => {
    // UI_TERM_LABELS maps DTE → 'DTE (Days to Expiration)'
    expect(html).toContain("DTE (Days to Expiration)");
  });

  it("includes the Trading Strategies evaluation framework list", () => {
    expect(html).toContain("ref-eval-list");
    expect(html).toContain("walk-forward, out-of-sample");
  });

  it("escapes HTML special characters in term definitions", () => {
    // Definitions containing & should be escaped to &amp; — the esc() helper
    // is exercised on all term/definition values pulled from the JSON asset.
    expect(html).not.toMatch(/<[^/a-zA-Z!]/); // no raw < outside valid tags
  });

  it("includes Finance expand-all toggle button", () => {
    expect(html).toContain("data-ref-card-toggle-all");
  });

  // ---------------------------------------------------------------------------
  // Software card
  // ---------------------------------------------------------------------------

  it("includes the Software card heading", () => {
    expect(html).toContain(">Software<");
  });

  it("renders the Projects in This Repository section", () => {
    expect(html).toContain("Projects in This Repository");
    // At least one project row from software.json
    expect(html).toContain("trading/");
  });

  it("renders the Languages and Frameworks section", () => {
    expect(html).toContain("Languages and Frameworks");
    expect(html).toContain("Python");
  });

  it("renders the Key Python Packages section with sub-group labels", () => {
    expect(html).toContain("Key Python Packages");
    expect(html).toContain("ref-subsection-label");
  });

  // ---------------------------------------------------------------------------
  // API card
  // ---------------------------------------------------------------------------

  it("includes the API Reference card heading", () => {
    expect(html).toContain("API Reference");
  });

  it("renders the API Basics section with the docs link", () => {
    expect(html).toContain("API Basics");
    expect(html).toContain('href="/docs"');
  });

  it("renders backtesting endpoint group", () => {
    expect(html).toContain("Backtesting Endpoints");
  });

  it("renders admin endpoint group with request body tables", () => {
    expect(html).toContain("Admin Endpoints");
    // ADMIN_REQUEST_BODY_CONTENT contains 'AdminCreateAccountRequest'
    expect(html).toContain("AdminCreateAccountRequest");
  });

  it("renders the backtest request body section", () => {
    // BACKTEST_REQUEST_BODY_SECTION is appended to the API card
    expect(html).toContain("BacktestRunRequest");
    expect(html).toContain("BacktestPreflightRequest");
    expect(html).toContain("WalkForwardRunRequest");
  });

  it("renders endpoint rows with method + path columns", () => {
    expect(html).toContain("ref-table--endpoint");
    expect(html).toContain("Method + Path");
  });

  it("includes Accounts &amp; Snapshots Endpoints group", () => {
    expect(html).toContain("Accounts");
    expect(html).toContain("Snapshots");
  });

  // ---------------------------------------------------------------------------
  // esc() helper — indirectly tested through rendered output
  // ---------------------------------------------------------------------------

  it("escapes ampersand in card headings (esc used on all string values)", () => {
    // buildFinanceCard uses esc() on section titles that contain &
    // Finance section order includes items mapped to 'Execution & Risk Controls'
    expect(html).toContain("Execution &amp; Risk Controls");
  });

  it("escapes angle brackets in software descriptions that contain them", () => {
    // If any asset value has a raw <, it should be escaped. Verify no raw <script>.
    expect(html).not.toContain("<script");
  });
});
