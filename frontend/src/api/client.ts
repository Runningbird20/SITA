import type { ApiErrorBody } from "./types";

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export interface HealthzResponse {
  status: "ok" | "degraded";
  database: "ok" | "unavailable";
  llm: "ok" | "unavailable" | "not_configured";
}

/** Thrown by apiFetch for any non-2xx response. Carries the structured
 * {"error": {code, message, details}} envelope every Phase 9 endpoint
 * guarantees, when the response body actually has one.
 */
export class ApiError extends Error {
  status: number;
  code: string | null;
  details: unknown;

  constructor(status: number, message: string, code: string | null, details: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function fetchJson<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { signal });
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return (await response.json()) as T;
}

/** Fetch helper for the real Phase 9/10 API surface — unlike fetchJson
 * above (kept as-is for the status page's /healthz and /openapi.json
 * checks), this decodes Phase 9's structured error envelope into a typed
 * ApiError so pages can show a real message instead of a bare status code.
 */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    let code: string | null = null;
    let message = `${path} returned ${response.status}`;
    let details: unknown = null;
    try {
      const body = (await response.json()) as ApiErrorBody;
      if (body?.error) {
        code = body.error.code;
        message = body.error.message;
        details = body.error.details;
      }
    } catch {
      // Response body wasn't JSON (or wasn't the expected shape) — fall
      // back to the generic message above rather than throwing a second
      // error out of the error handler.
    }
    throw new ApiError(response.status, message, code, details);
  }
  return (await response.json()) as T;
}

function buildQuery(params?: Record<string, string | number | boolean | undefined | null>): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export { buildQuery };

export function fetchHealthz(signal: AbortSignal): Promise<HealthzResponse> {
  return fetchJson<HealthzResponse>("/healthz", signal);
}

interface OpenApiSchema {
  paths?: Record<string, unknown>;
}

/** The set of API route paths FastAPI currently has mounted, read from its
 * auto-generated OpenAPI schema — a live, honest way to tell "is this
 * route actually registered" apart from "is this route documented
 * somewhere," with zero backend changes required to support it.
 */
export async function fetchOpenApiPaths(signal: AbortSignal): Promise<Set<string>> {
  const schema = await fetchJson<OpenApiSchema>("/openapi.json", signal);
  return new Set(Object.keys(schema.paths ?? {}));
}

/** Phase 13's /metrics is unversioned Prometheus text, not JSON, and isn't
 * listed in the OpenAPI schema (it's registered with include_in_schema
 * =False, matching Prometheus's own scrape convention) — so it needs its
 * own check rather than reusing fetchJson/fetchOpenApiPaths. Never rejects:
 * a /metrics hiccup should mark only Phase 13 broken, not take down the
 * whole status page via a failed Promise.all.
 */
export async function fetchMetricsAvailable(signal: AbortSignal): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/metrics`, { signal });
    if (!response.ok) return false;
    const text = await response.text();
    // A metric declared with no labels (unlike the labeled counters) is
    // always emitted from process start, even before any pipeline activity
    // — a reliable "is this really Prometheus output" signal.
    return text.includes("sita_incidents_created_total");
  } catch {
    return false;
  }
}
