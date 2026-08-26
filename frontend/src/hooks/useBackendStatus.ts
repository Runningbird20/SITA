import { useCallback, useEffect, useState } from "react";
import {
  fetchHealthz,
  fetchMetricsAvailable,
  fetchOpenApiPaths,
  type HealthzResponse,
} from "../api/client";

export interface BackendStatus {
  /** True once the first check has resolved (success or failure). */
  loading: boolean;
  /** True if the backend answered at all (even if degraded). */
  reachable: boolean;
  healthz: HealthzResponse | null;
  openApiPaths: Set<string> | null;
  /** Whether GET /metrics returned real Prometheus output. Never causes
   * the whole status check to fail — see fetchMetricsAvailable. */
  metricsAvailable: boolean;
  error: string | null;
  checkedAt: Date | null;
  refresh: () => void;
}

const REQUEST_TIMEOUT_MS = 5000;

export function useBackendStatus(pollIntervalMs = 15000): BackendStatus {
  const [state, setState] = useState<Omit<BackendStatus, "refresh">>({
    loading: true,
    reachable: false,
    healthz: null,
    openApiPaths: null,
    metricsAvailable: false,
    error: null,
    checkedAt: null,
  });

  const check = useCallback(() => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    Promise.all([
      fetchHealthz(controller.signal),
      fetchOpenApiPaths(controller.signal),
      fetchMetricsAvailable(controller.signal),
    ])
      .then(([healthz, openApiPaths, metricsAvailable]) => {
        setState({
          loading: false,
          reachable: true,
          healthz,
          openApiPaths,
          metricsAvailable,
          error: null,
          checkedAt: new Date(),
        });
      })
      .catch((err: unknown) => {
        setState({
          loading: false,
          reachable: false,
          healthz: null,
          openApiPaths: null,
          metricsAvailable: false,
          error: err instanceof Error ? err.message : "Unknown error",
          checkedAt: new Date(),
        });
      })
      .finally(() => clearTimeout(timeoutId));

    return () => {
      clearTimeout(timeoutId);
      controller.abort();
    };
  }, []);

  useEffect(() => {
    const cancel = check();
    const interval = setInterval(check, pollIntervalMs);
    return () => {
      cancel();
      clearInterval(interval);
    };
  }, [check, pollIntervalMs]);

  return { ...state, refresh: check };
}
