import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthContext } from "./AuthContext";
import { Layout } from "./Layout";

function renderLayout(
  user: { username: string; role: "admin" | "analyst" } | null,
  logout = vi.fn(),
) {
  return render(
    <AuthContext.Provider value={{ user: user as never, logout }}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<div>page content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Layout — admin-only action buttons", () => {
  it("shows Run pipeline and Reanalyze when auth is disabled (user is null)", () => {
    renderLayout(null);
    expect(screen.getByRole("button", { name: /run pipeline/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^reanalyze$/i })).toBeInTheDocument();
  });

  it("shows Run pipeline and Reanalyze for an admin", () => {
    renderLayout({ username: "admin1", role: "admin" });
    expect(screen.getByRole("button", { name: /run pipeline/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^reanalyze$/i })).toBeInTheDocument();
  });

  it("hides both Run pipeline and Reanalyze for an analyst", () => {
    renderLayout({ username: "analyst1", role: "analyst" });
    expect(screen.queryByRole("button", { name: /run pipeline/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^reanalyze$/i })).not.toBeInTheDocument();
  });

  it("Reanalyze calls the reanalyze endpoint and shows the resulting summary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        return new Response(
          JSON.stringify({
            since: null,
            incidents_processed: 3,
            analysis_results_created: 18,
            analysis_results_skipped: 0,
            recommendations_created: 4,
            mitre_mappings_created: 2,
            by_task_type: {},
          }),
          { status: 200 },
        );
      }),
    );
    const user = userEvent.setup();
    renderLayout(null);

    await user.click(screen.getByRole("button", { name: /^reanalyze$/i }));

    await screen.findByText(/18 AI result\(s\) regenerated across 3 incident\(s\)/i);
  });
});

describe("Layout — current user / logout", () => {
  it("shows nothing user-related when auth is disabled", () => {
    renderLayout(null);
    expect(screen.queryByText(/log out/i)).not.toBeInTheDocument();
  });

  it("shows the username, role, and a working logout control when signed in", async () => {
    const logout = vi.fn();
    const user = userEvent.setup();
    renderLayout({ username: "analyst1", role: "analyst" }, logout);

    expect(screen.getByText("analyst1")).toBeInTheDocument();
    expect(screen.getByText("(analyst)")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /log out/i }));
    expect(logout).toHaveBeenCalledOnce();
  });
});
