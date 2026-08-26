import { useEffect, useState } from "react";
import { ApiError, clearAuthToken, setAuthToken } from "../api/client";
import { fetchMe, login as loginRequest, logout as logoutRequest } from "../api/resources";
import type { User } from "../api/types";
import { AuthContext } from "./AuthContext";
import "./AuthGate.css";

type GateState = "checking" | "authorized" | "unauthorized";

/** Wraps the dashboard routes (not /status, which stays reachable for
 * diagnostics the same way /healthz does — see App.tsx). GET /auth/me
 * returns null when auth is disabled (no User rows configured — the
 * default) and 401s only when auth is enabled and the request has no
 * valid session token, so a single probe tells this component everything
 * it needs: whether to show a login form at all, and who's signed in if
 * not. See DEF.md § Phase 14.
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<GateState>("checking");
  const [user, setUser] = useState<User | null>(null);
  const [usernameInput, setUsernameInput] = useState("");
  const [passwordInput, setPasswordInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchMe()
      .then((me) => {
        if (cancelled) return;
        setUser(me);
        setState("authorized");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        // A 401 means a login is required — anything else (network
        // error, backend unreachable) shouldn't permanently lock the
        // dashboard behind a form it can't even verify against.
        setState(err instanceof ApiError && err.status === 401 ? "unauthorized" : "authorized");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setState("checking");
    loginRequest(usernameInput.trim(), passwordInput)
      .then((response) => {
        setAuthToken(response.token);
        setUser(response.user);
        setState("authorized");
      })
      .catch(() => {
        setError("Invalid username or password.");
        setState("unauthorized");
      });
  }

  function handleLogout() {
    // Best-effort: the session is cleared locally regardless of whether
    // the revoke call itself succeeds (e.g. the backend is unreachable) —
    // a user asking to log out shouldn't get stuck logged in over a
    // network blip.
    logoutRequest().catch(() => {});
    clearAuthToken();
    setUser(null);
    setUsernameInput("");
    setPasswordInput("");
    setState("unauthorized");
  }

  if (state === "checking") {
    return <div className="auth-gate-checking">Checking backend access…</div>;
  }

  if (state === "unauthorized") {
    return (
      <div className="auth-gate">
        <form className="auth-gate-form" onSubmit={handleSubmit}>
          <h1>SITA</h1>
          <p>Sign in to continue.</p>
          <input
            type="text"
            value={usernameInput}
            onChange={(e) => setUsernameInput(e.target.value)}
            placeholder="Username"
            autoFocus
          />
          <input
            type="password"
            value={passwordInput}
            onChange={(e) => setPasswordInput(e.target.value)}
            placeholder="Password"
          />
          <button type="submit" disabled={!usernameInput.trim() || !passwordInput}>
            Sign in
          </button>
          {error && <p className="auth-gate-error">{error}</p>}
        </form>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ user, logout: handleLogout }}>{children}</AuthContext.Provider>
  );
}
