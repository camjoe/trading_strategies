const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function postJson<T>(path: string, payload?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: payload ? { "Content-Type": "application/json" } : undefined,
    body: payload ? JSON.stringify(payload) : undefined,
  });
  if (!res.ok) {
    let detail = "";
    try {
      const maybeJson = (await res.json()) as { detail?: string };
      detail = typeof maybeJson.detail === "string" ? maybeJson.detail : "";
    } catch {
      detail = "";
    }
    throw new Error(detail ? `Request failed: ${res.status} (${detail})` : `Request failed: ${res.status}`);
  }
  const text = await res.text();
  return (text ? (JSON.parse(text) as T) : ({} as T));
}
