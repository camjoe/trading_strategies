export const EXPAND_ALL_ICON = "⊞";
export const COLLAPSE_ALL_ICON = "⊟";

const DOCS_GROUP_LABEL_OVERRIDES: Record<string, string> = {
  "Financial & Market Knowledge": "Financial & Markets",
  "RESTful API Reference": "API Reference",
};

export function getDocsGroupDisplayLabel(groupLabel: string): string {
  return DOCS_GROUP_LABEL_OVERRIDES[groupLabel] ?? groupLabel;
}
