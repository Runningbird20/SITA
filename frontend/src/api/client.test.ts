import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch, clearAuthToken, getAuthToken, setAuthToken } from "./client";

describe("auth token storage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns null when nothing is stored", () => {
    expect(getAuthToken()).toBeNull();
  });

  it("round-trips a stored token", () => {
    setAuthToken("abc123");
    expect(getAuthToken()).toBe("abc123");
  });

  it("clearAuthToken removes it", () => {
    setAuthToken("abc123");
    clearAuthToken();
    expect(getAuthToken()).toBeNull();
  });
});

describe("apiFetch Authorization header", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("attaches Authorization: Bearer <token> when a token is stored", async () => {
    setAuthToken("my-token");
    let capturedHeaders: Headers | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        capturedHeaders = new Headers(init?.headers);
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      }),
    );

    await apiFetch("/api/v1/incidents");

    expect(capturedHeaders?.get("Authorization")).toBe("Bearer my-token");
  });

  it("sends no Authorization header when no token is stored", async () => {
    let capturedHeaders: Headers | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        capturedHeaders = new Headers(init?.headers);
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      }),
    );

    await apiFetch("/api/v1/incidents");

    expect(capturedHeaders?.has("Authorization")).toBe(false);
  });

  it("resolves with undefined for a 204 No Content response, not a JSON parse error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 204 })),
    );

    await expect(
      apiFetch("/api/v1/analysis-results/some-id/feedback", { method: "DELETE" }),
    ).resolves.toBeUndefined();
  });
});
