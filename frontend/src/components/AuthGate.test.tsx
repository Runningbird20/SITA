import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getAuthToken } from "../api/client";
import { AuthGate } from "./AuthGate";

function stubFetchOnce(status: number, body: unknown = null) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  );
}

const ADMIN_USER = {
  id: "user-1",
  username: "admin1",
  role: "admin",
  created_at: "2026-01-01T00:00:00Z",
};

describe("AuthGate", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders children immediately when /auth/me returns null (auth disabled)", async () => {
    stubFetchOnce(200, null);

    render(
      <AuthGate>
        <div>dashboard content</div>
      </AuthGate>,
    );

    await waitFor(() => expect(screen.getByText("dashboard content")).toBeInTheDocument());
  });

  it("renders children immediately when /auth/me returns an already-logged-in user", async () => {
    stubFetchOnce(200, ADMIN_USER);

    render(
      <AuthGate>
        <div>dashboard content</div>
      </AuthGate>,
    );

    await waitFor(() => expect(screen.getByText("dashboard content")).toBeInTheDocument());
  });

  it("shows a login form when /auth/me returns 401", async () => {
    stubFetchOnce(401, { error: { code: "unauthorized", message: "nope", details: null } });

    render(
      <AuthGate>
        <div>dashboard content</div>
      </AuthGate>,
    );

    await waitFor(() => expect(screen.getByPlaceholderText("Username")).toBeInTheDocument());
    expect(screen.getByPlaceholderText("Password")).toBeInTheDocument();
    expect(screen.queryByText("dashboard content")).not.toBeInTheDocument();
  });

  it("submitting correct credentials stores the token and reveals the dashboard", async () => {
    stubFetchOnce(401, { error: { code: "unauthorized", message: "nope", details: null } });
    const user = userEvent.setup();

    render(
      <AuthGate>
        <div>dashboard content</div>
      </AuthGate>,
    );

    await waitFor(() => expect(screen.getByPlaceholderText("Username")).toBeInTheDocument());

    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              token: "issued-token",
              user: ADMIN_USER,
              expires_at: "2026-02-01T00:00:00Z",
            }),
            { status: 200 },
          ),
      ),
    );

    await user.type(screen.getByPlaceholderText("Username"), "admin1");
    await user.type(screen.getByPlaceholderText("Password"), "correct-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(screen.getByText("dashboard content")).toBeInTheDocument());
    expect(getAuthToken()).toBe("issued-token");
  });

  it("shows an error and stays on the form when login is rejected", async () => {
    stubFetchOnce(401, { error: { code: "unauthorized", message: "nope", details: null } });
    const user = userEvent.setup();

    render(
      <AuthGate>
        <div>dashboard content</div>
      </AuthGate>,
    );

    await waitFor(() => expect(screen.getByPlaceholderText("Username")).toBeInTheDocument());

    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error: {
                code: "unauthorized",
                message: "Invalid username or password",
                details: null,
              },
            }),
            { status: 401 },
          ),
      ),
    );

    await user.type(screen.getByPlaceholderText("Username"), "admin1");
    await user.type(screen.getByPlaceholderText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() =>
      expect(screen.getByText(/invalid username or password/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText("dashboard content")).not.toBeInTheDocument();
  });
});
