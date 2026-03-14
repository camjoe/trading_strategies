export const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export function pct(v: number): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

export function num(v: number): string {
  return `${v >= 0 ? "+" : ""}${currency.format(v)}`;
}

export function esc(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
