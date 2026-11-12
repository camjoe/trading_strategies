import { describe, expect, it } from "vitest";

const TOKENS_FILE = "tokens.css";

const STYLE_SOURCES = import.meta.glob<string>("../../styles/*.css", {
  query: "?raw",
  import: "default",
  eager: true,
});

function readStyles(): Map<string, string> {
  return new Map(Object.entries(STYLE_SOURCES).map(([path, css]) => [path.split("/").pop() ?? path, css]));
}

function declaredNames(block: string): Set<string> {
  return new Set([...block.matchAll(/^\s*(--[\w-]+)\s*:/gm)].map((match) => match[1]));
}

function themeBlocks(tokens: string): { light: Set<string>; dark: Set<string> } {
  const blocks = [...tokens.matchAll(/(:root(?:\[data-theme="dark"\])?)\s*\{([^}]*)\}/g)];
  const darkIndex = blocks.findIndex((match) => match[1].includes("data-theme"));
  expect(darkIndex).toBeGreaterThan(0);
  return { light: declaredNames(blocks[darkIndex - 1][2]), dark: declaredNames(blocks[darkIndex][2]) };
}

describe("theme tokens", () => {
  const styles = readStyles();
  const tokens = styles.get(TOKENS_FILE) ?? "";

  it("defines the same inputs in the light and dark themes", () => {
    const { light, dark } = themeBlocks(tokens);
    expect([...light].filter((name) => !dark.has(name))).toEqual([]);
    expect([...dark].filter((name) => !light.has(name))).toEqual([]);
  });

  it("defines every variable that a stylesheet reads without a fallback", () => {
    const defined = new Set<string>();
    for (const css of styles.values()) {
      declaredNames(css).forEach((name) => defined.add(name));
    }
    const undefinedUses: string[] = [];
    for (const [file, css] of styles) {
      for (const match of css.matchAll(/var\((--[\w-]+)\s*\)/g)) {
        if (!defined.has(match[1])) undefinedUses.push(`${file}: ${match[1]}`);
      }
    }
    expect(undefinedUses).toEqual([]);
  });

  it("keeps theme colors out of the other stylesheets", () => {
    const literals: string[] = [];
    for (const [file, css] of styles) {
      if (file === TOKENS_FILE) continue;
      for (const match of css.matchAll(/#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)/g)) {
        literals.push(`${file}: ${match[0]}`);
      }
    }
    expect(literals).toEqual(["autonomy-monitor.css: rgba(0, 0, 0, 0.3)"]);
  });
});
