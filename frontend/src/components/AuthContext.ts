import { createContext, useContext } from "react";
import type { User } from "../api/types";

export interface AuthContextValue {
  /** null both when auth is disabled (no users configured) and briefly
   * during the initial probe — components that only care "is anyone
   * gating me right now" (e.g. showing a name) can treat both the same;
   * components that need to distinguish should check AuthGate's own
   * loading state instead, which nothing outside this file currently
   * needs to.
   */
  user: User | null;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue>({ user: null, logout: () => {} });

/** Current user (or null if auth is disabled) and a logout action —
 * available to every route AuthGate wraps. See DEF.md § Phase 14,
 * "Multi-user / RBAC (post-roadmap)".
 */
export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}
