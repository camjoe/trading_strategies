const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

async function parseErrorDetail(res: Response): Promise<string> {
  try {
    const maybeJson = (await res.json()) as { detail?: string };
    return typeof maybeJson.detail === "string" ? maybeJson.detail : "";
  } catch {
    return "";
  }
}

async function assertOk(res: Response, includeDetail: boolean): Promise<void> {
  if (res.ok) {
    return;
  }

  const detail = includeDetail ? await parseErrorDetail(res) : "";
  throw new Error(detail ? `Request failed: ${res.status} (${detail})` : `Request failed: ${res.status}`);
}

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(apiUrl(path));
  await assertOk(res, false);
  return (await res.json()) as T;
}

export async function patchJson<T>(path: string, payload: unknown): Promise<T> {
  const res = await fetch(apiUrl(path), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await assertOk(res, true);

  const text = await res.text();
  return (text ? (JSON.parse(text) as T) : ({} as T));
}

export async function postJson<T>(path: string, payload?: unknown): Promise<T> {
  const res = await fetch(apiUrl(path), {
    method: "POST",
    headers: payload ? { "Content-Type": "application/json" } : undefined,
    body: payload ? JSON.stringify(payload) : undefined,
  });
  await assertOk(res, true);

  const text = await res.text();
  return (text ? (JSON.parse(text) as T) : ({} as T));
}
