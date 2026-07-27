// Bare glyphs, matching the per-section toggles in docs.css: the boxed forms
// (⊞/⊟) draw their own square, which reads as a border inside the round button
// and crowds the sign itself.
export const EXPAND_ALL_ICON = "+";
export const COLLAPSE_ALL_ICON = "−";

const DOCS_GROUP_LABEL_OVERRIDES: Record<string, string> = {
  "Financial & Market Knowledge": "Financial & Markets",
  "RESTful API Reference": "API Reference",
};

export function getDocsGroupDisplayLabel(groupLabel: string): string {
  return DOCS_GROUP_LABEL_OVERRIDES[groupLabel] ?? groupLabel;
}
