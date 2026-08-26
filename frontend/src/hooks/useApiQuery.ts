import { useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";

export interface ApiQueryState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

interface QueryResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

/** One shared data-fetching hook, used by every real dashboard page —
 * mirrors the shape useBackendStatus already established (loading/data/
 * error/refetch). No client-side cache library: ~8 independent views each
 * fetching once per navigation isn't the shared-cache/background-refetch
 * problem a library like that earns its keep solving. See DEF.md § Phase 10.
 */
export function useApiQuery<T>(fetcher: () => Promise<T>, deps: unknown[]): ApiQueryState<T> {
  const [state, setState] = useState<QueryResult<T>>({ data: null, loading: true, error: null });
  const [tick, setTick] = useState(0);

  // Refs are only ever written from effects (never during render) so the
  // main fetch effect below can read the latest fetcher without needing
  // callers to memoize it or without listing it in the deps array.
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  useEffect(() => {
    let cancelled = false;

    async function run() {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const result = await fetcherRef.current();
        if (!cancelled) setState({ data: result, loading: false, error: null });
      } catch (err) {
        if (!cancelled) {
          setState({
            data: null,
            loading: false,
            error: err instanceof ApiError ? err.message : "Failed to load data",
          });
        }
      }
    }

    void run();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { ...state, refetch: () => setTick((t) => t + 1) };
}
