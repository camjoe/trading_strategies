import { describe, expect, it } from "vitest";

import { warningListHtml } from "./backtesting";

describe("warningListHtml", () => {
  it("renders an empty-state message when no warnings exist", () => {
    const html = warningListHtml([]);
    expect(html).toContain("No financial-model warnings");
  });

  it("escapes warning text to avoid HTML injection", () => {
    const html = warningListHtml(["<script>alert('xss')</script>"]);
    expect(html).toContain("&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;");
    expect(html).not.toContain("<script>");
  });
});
