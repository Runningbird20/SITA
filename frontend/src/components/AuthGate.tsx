import { useEffect, useState } from "react";
import { apiFetch, ApiError, setAuthToken } from "../api/client";
import "./AuthGate.css";

type GateState = "checking" | "authorized" | "unauthorized";

/** Wraps the dashboard routes (not /status, which stays reachable for
 * diagnostics the same way /healthz does — see App.tsx). See DEF.md §
 * Phase 14: the backend's auth is opt-in (API_AUTH_TOKEN unset by
 * default), so this probe succeeds with no token and the gate never
 * appears for the default local-dev path.
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<GateState>("checking");
  const [tokenInput, setTokenInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch("/api/v1/incidents?limit=1")
      .then(() => {
        if (!cancelled) setState("authorized");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        // A 401 means auth is required — anything else (network error,
        // backend unreachable) shouldn't permanently lock the dashboard
        // behind a token form it can't even verify against.
        setState(err instanceof ApiError && err.status === 401 ? "unauthorized" : "authorized");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setAuthToken(tokenInput.trim());
    setError(null);
    setState("checking");
    apiFetch("/api/v1/incidents?limit=1")
      .then(() => setState("authorized"))
      .catch(() => {
        setError("That token was rejected. Check it and try again.");
        setState("unauthorized");
      });
  }

  if (state === "checking") {
    return <div className="auth-gate-checking">Checking backend access…</div>;
  }

  if (state === "unauthorized") {
    return (
      <div className="auth-gate">
        <form className="auth-gate-form" onSubmit={handleSubmit}>
          <h1>SITA</h1>
          <p>This backend requires an API token.</p>
          <input
            type="password"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            placeholder="API token"
            autoFocus
          />
          <button type="submit" disabled={!tokenInput.trim()}>
            Continue
          </button>
          {error && <p className="auth-gate-error">{error}</p>}
        </form>
      </div>
    );
  }

  return children;
}
