function esc(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function classifyLogLine(line: string): string {
  const upper = line.toUpperCase();
  if (upper.includes("ERROR") || upper.includes("FAILED") || upper.includes("EXCEPTION") || upper.includes("TRACEBACK")) {
    return "error";
  }
  if (upper.includes("WARN")) {
    return "warn";
  }
  if (upper.includes("DONE") || upper.includes("COMPLETE") || upper.includes("SUCCESS")) {
    return "ok";
  }
  if (upper.includes("START") || upper.includes("RUN META")) {
    return "meta";
  }
  return "plain";
}

function sanitizeLogLine(line: string): string {
  // Remove BOM, ANSI escape codes, and low control chars that can render as artifacts.
  return line
    .replace(/^\uFEFF/, "")
    .replace(/\u001B\[[0-9;]*[A-Za-z]/g, "")
    .replace(/\r/g, "")
    .replace(/[\uFFFD]/g, "")
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "");
}

export function renderLogLines(lines: string[]): string {
  const cleaned = lines.map(sanitizeLogLine).filter((line) => line.trim().length > 0);

  if (!cleaned.length) {
    return '<div class="log-empty">No lines matched this filter.</div>';
  }

  let html = "";
  let inGroup = false;

  const closeGroup = (): void => {
    if (inGroup) {
      html += "</details>";
      inGroup = false;
    }
  };

  for (const line of cleaned) {
    const kind = classifyLogLine(line);

    if (kind === "meta") {
      closeGroup();
      html += `<details class="log-group" open><summary class="log-meta-line">${esc(line)}</summary>`;
      inGroup = true;
      continue;
    }

    html += `<div class="log-line log-${kind}"><span class="log-text">${esc(line)}</span></div>`;
  }

  closeGroup();
  return html;
}
