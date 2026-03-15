import { afterEach, describe, expect, it, vi } from "vitest";

import { getJson, postJson } from "./http";

describe("http helpers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("getJson returns parsed JSON on success", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await getJson<{ ok: boolean }>("/api/test");
    expect(result).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("getJson throws on non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) }),
    );

    await expect(getJson("/api/fail")).rejects.toThrow("Request failed: 500");
  });

  it("postJson sends payload and returns parsed JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => '{"saved":true}',
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await postJson<{ saved: boolean }>("/api/save", { x: 1 });
    expect(result).toEqual({ saved: true });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/save"),
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ x: 1 }),
      }),
    );
  });

  it("postJson returns empty object when response body is empty", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
        text: async () => "",
      }),
    );

    await expect(postJson("/api/empty")).resolves.toEqual({});
  });

  it("postJson includes backend detail when available", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: async () => ({ detail: "bad input" }),
      }),
    );

    await expect(postJson("/api/fail", { bad: true })).rejects.toThrow(
      "Request failed: 400 (bad input)",
    );
  });
});
