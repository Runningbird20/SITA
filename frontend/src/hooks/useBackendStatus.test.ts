import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { useBackendStatus } from "./useBackendStatus";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useBackendStatus", () => {
  it("starts loading and unreachable", () => {
    vi.spyOn(client, "fetchHealthz").mockReturnValue(new Promise(() => {}));
    vi.spyOn(client, "fetchOpenApiPaths").mockReturnValue(new Promise(() => {}));
    vi.spyOn(client, "fetchMetricsAvailable").mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useBackendStatus(1_000_000));
    expect(result.current.loading).toBe(true);
    expect(result.current.reachable).toBe(false);
  });

  it("reports reachable with the resolved data on success", async () => {
    const healthz = { status: "ok" as const, database: "ok" as const, llm: "ok" as const };
    vi.spyOn(client, "fetchHealthz").mockResolvedValue(healthz);
    vi.spyOn(client, "fetchOpenApiPaths").mockResolvedValue(new Set(["/api/v1/incidents"]));
    vi.spyOn(client, "fetchMetricsAvailable").mockResolvedValue(true);

    const { result } = renderHook(() => useBackendStatus(1_000_000));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.reachable).toBe(true);
    expect(result.current.healthz).toEqual(healthz);
    expect(result.current.openApiPaths?.has("/api/v1/incidents")).toBe(true);
    expect(result.current.metricsAvailable).toBe(true);
    expect(result.current.checkedAt).toBeInstanceOf(Date);
  });

  it("reports unreachable with an error message on failure", async () => {
    vi.spyOn(client, "fetchHealthz").mockRejectedValue(new Error("network down"));
    vi.spyOn(client, "fetchOpenApiPaths").mockResolvedValue(new Set());
    vi.spyOn(client, "fetchMetricsAvailable").mockResolvedValue(false);

    const { result } = renderHook(() => useBackendStatus(1_000_000));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.reachable).toBe(false);
    expect(result.current.error).toBe("network down");
  });

  it("refresh() re-runs the checks", async () => {
    const fetchHealthz = vi
      .spyOn(client, "fetchHealthz")
      .mockResolvedValue({ status: "ok", database: "ok", llm: "ok" });
    vi.spyOn(client, "fetchOpenApiPaths").mockResolvedValue(new Set());
    vi.spyOn(client, "fetchMetricsAvailable").mockResolvedValue(false);

    const { result } = renderHook(() => useBackendStatus(1_000_000));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fetchHealthz).toHaveBeenCalledOnce();

    result.current.refresh();
    await waitFor(() => expect(fetchHealthz).toHaveBeenCalledTimes(2));
  });
});
