import { describe, expect, it } from "vitest";

import type { AccountListItem } from "../../types";
import { accountCard } from "../../components/accounts";

describe("accountCard", () => {
  it("renders account stats with positive styling", () => {
    const account: AccountListItem = {
      name: "acct1",
      displayName: "Growth",
      strategy: "Momentum",
      instrumentMode: "equity",
      benchmark: "SPY",
      equity: 10500,
      totalChange: 500,
      totalChangePct: 5,
      changeSinceLastSnapshot: 10,
      latestSnapshotTime: "2026-03-15T00:00:00Z",
    };

    const html = accountCard(account);
    expect(html).toContain("Growth");
    expect(html).toContain("Momentum");
    expect(html).toContain("row up");
    expect(html).toContain("acct1");
  });

  it("escapes text and handles null snapshot change", () => {
    const account: AccountListItem = {
      name: "acct<script>",
      displayName: "Display",
      strategy: "MeanReversion",
      instrumentMode: "equity",
      benchmark: "QQQ",
      equity: 900,
      totalChange: -100,
      totalChangePct: -10,
      changeSinceLastSnapshot: null,
      latestSnapshotTime: null,
    };

    const html = accountCard(account);
    expect(html).not.toContain("<script>");
    expect(html).toContain("n/a");
    expect(html).toContain("none");
    expect(html).toContain("row down");
  });
});
