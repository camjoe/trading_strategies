// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";

import { currentTheme, initTheme, toggleTheme } from "../../lib/theme";

describe("theme", () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  it("defaults to dark when no choice is saved", () => {
    initTheme();

    expect(currentTheme()).toBe("dark");
  });

  it("uses a saved choice over the default", () => {
    localStorage.setItem("trading-ui-theme", "light");
    initTheme();

    expect(currentTheme()).toBe("light");
  });

  it("saves the toggled theme for the next load", () => {
    initTheme();

    expect(toggleTheme()).toBe("light");
    expect(localStorage.getItem("trading-ui-theme")).toBe("light");
  });
});
