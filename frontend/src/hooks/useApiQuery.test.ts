import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { useApiQuery } from "./useApiQuery";

describe("useApiQuery", () => {
  it("starts in a loading state with no data", () => {
    const { result } = renderHook(() => useApiQuery(() => new Promise(() => {}), []));
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("resolves with data on success", async () => {
    const { result } = renderHook(() => useApiQuery(() => Promise.resolve({ x: 1 }), []));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual({ x: 1 });
    expect(result.current.error).toBeNull();
  });

  it("surfaces an ApiError's message on failure", async () => {
    const fetcher = () => Promise.reject(new ApiError(404, "not found", "not_found", null));
    const { result } = renderHook(() => useApiQuery(fetcher, []));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBe("not found");
  });

  it("falls back to a generic message for a non-ApiError failure", async () => {
    const fetcher = () => Promise.reject(new Error("boom"));
    const { result } = renderHook(() => useApiQuery(fetcher, []));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe("Failed to load data");
  });

  it("refetch() triggers the fetcher again", async () => {
    const fetcher = vi.fn().mockResolvedValue({ x: 1 });
    const { result } = renderHook(() => useApiQuery(fetcher, []));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fetcher).toHaveBeenCalledOnce();

    result.current.refetch();
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  });

  it("re-runs the fetcher when a dependency changes", async () => {
    const fetcher = vi.fn().mockResolvedValue({ x: 1 });
    const { rerender } = renderHook(({ dep }) => useApiQuery(fetcher, [dep]), {
      initialProps: { dep: 1 },
    });

    await waitFor(() => expect(fetcher).toHaveBeenCalledOnce());

    rerender({ dep: 2 });
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  });
});
