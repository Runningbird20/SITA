export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export interface HealthzResponse {
  status: "ok" | "degraded";
  database: "ok" | "unavailable";
}

async function fetchJson<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { signal });
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return (await response.json()) as T;
}

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
