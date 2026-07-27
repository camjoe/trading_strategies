import { describe, expect, it } from "vitest";

import { renderParameterGroups } from "../../components/admin-parameters";

describe("renderParameterGroups", () => {
  const groups = [
    {
      scope: "global / trade throttle",
      note: "no settings row - code defaults apply",
      entries: [
        { name: "max_trades_per_day", value: "none", source: "default" },
      ],
    },
    {
      scope: "account alpha / book core / rotation",
      note: null,
      entries: [
        { name: "cooldown_days", value: "14", source: "db" },
        { name: "stability_weight", value: "0.25", source: "default" },
      ],
    },
  ];

  it("renders scopes, values, sources, and fallback notes", () => {
    const result = renderParameterGroups(groups, "", "");
    expect(result.groupCount).toBe(2);
    expect(result.entryCount).toBe(3);
    expect(result.html).toContain("global / trade throttle");
    expect(result.html).toContain("code defaults apply");
    expect(result.html).toContain("cooldown_days");
    expect(result.html).toContain(">db<");
  });

  it("filters by search and source", () => {
    const result = renderParameterGroups(groups, "rotation", "db");
    expect(result.groupCount).toBe(1);
    expect(result.entryCount).toBe(1);
    expect(result.html).toContain("cooldown_days");
    expect(result.html).not.toContain("stability_weight");
  });
});
