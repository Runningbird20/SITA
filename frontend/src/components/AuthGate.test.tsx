import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getAuthToken } from "../api/client";
import { AuthGate } from "./AuthGate";

function stubFetchOnce(status: number, body: unknown = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  );
}

describe("AuthGate", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders children immediately once the probe succeeds (no auth configured)", async () => {
    stubFetchOnce(200, { items: [] });

    render(
      <AuthGate>
        <div>dashboard content</div>
      </AuthGate>,
    );

    await waitFor(() => expect(screen.getByText("dashboard content")).toBeInTheDocument());
  });

  it("shows a token form when the probe returns 401", async () => {
    stubFetchOnce(401, { error: { code: "unauthorized", message: "nope", details: null } });

    render(
      <AuthGate>
        <div>dashboard content</div>
      </AuthGate>,
    );

    await waitFor(() => expect(screen.getByPlaceholderText("API token")).toBeInTheDocument());
    expect(screen.queryByText("dashboard content")).not.toBeInTheDocument();
  });

  it("submitting the correct token stores it and reveals the dashboard", async () => {
    stubFetchOnce(401, { error: { code: "unauthorized", message: "nope", details: null } });
    const user = userEvent.setup();

    render(
      <AuthGate>
        <div>dashboard content</div>
      </AuthGate>,
    );

    await waitFor(() => expect(screen.getByPlaceholderText("API token")).toBeInTheDocument());

    // Next fetch (triggered by submit) succeeds.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ items: [] }), { status: 200 })),
    );

    await user.type(screen.getByPlaceholderText("API token"), "correct-token");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => expect(screen.getByText("dashboard content")).toBeInTheDocument());
    expect(getAuthToken()).toBe("correct-token");
  });

  it("shows an error and stays on the form when the submitted token is rejected", async () => {
    stubFetchOnce(401, { error: { code: "unauthorized", message: "nope", details: null } });
    const user = userEvent.setup();

    render(
      <AuthGate>
        <div>dashboard content</div>
      </AuthGate>,
    );

    await waitFor(() => expect(screen.getByPlaceholderText("API token")).toBeInTheDocument());

    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ error: { code: "unauthorized", message: "nope", details: null } }),
            { status: 401 },
          ),
      ),
    );

    await user.type(screen.getByPlaceholderText("API token"), "wrong-token");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => expect(screen.getByText(/rejected/i)).toBeInTheDocument());
    expect(screen.queryByText("dashboard content")).not.toBeInTheDocument();
  });
});
