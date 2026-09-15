import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Detection, TuningSuggestion } from "../../api/types";
import { TuningSuggestionsPanel } from "./TuningSuggestionsPanel";

afterEach(() => {
  vi.unstubAllGlobals();
});

const DETECTION: Detection = {
  id: "det-1",
  rule_key: "ssh_brute_force",
  name: "SSH Brute Force",
  description: "desc",
  category: "authentication",
  default_severity: "high",
  enabled: true,
  config: { failure_threshold: 10 },
  created_at: "2026-01-15T03:00:00Z",
};

const SUGGESTION: TuningSuggestion = {
  rule_key: "ssh_brute_force",
  rule_name: "SSH Brute Force",
  total_alerts: 10,
  false_positive_count: 6,
  false_positive_rate: 0.6,
  threshold_key: "failure_threshold",
  current_threshold_value: 10,
  suggested_threshold_value: 12,
  rationale: "6 of 10 alerts (60%) were marked false positive.",
};

describe("TuningSuggestionsPanel", () => {
  it("shows a loading state, then renders nothing once there are no suggestions", () => {
    const { container, rerender } = render(
      <TuningSuggestionsPanel
        suggestions={[]}
        loading={true}
        detectionsByRuleKey={new Map()}
        onApplied={() => {}}
      />,
    );
    expect(screen.getByText(/checking for tuning suggestions/i)).toBeInTheDocument();

    rerender(
      <TuningSuggestionsPanel
        suggestions={[]}
        loading={false}
        detectionsByRuleKey={new Map()}
        onApplied={() => {}}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a suggestion's rationale and applies it via PATCH", async () => {
    const fetchMock = vi.fn(async () => {
      return new Response(JSON.stringify({ ...DETECTION, config: { failure_threshold: 12 } }), {
        status: 200,
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const onApplied = vi.fn();
    const user = userEvent.setup();

    render(
      <TuningSuggestionsPanel
        suggestions={[SUGGESTION]}
        loading={false}
        detectionsByRuleKey={new Map([["ssh_brute_force", DETECTION]])}
        onApplied={onApplied}
      />,
    );

    expect(screen.getByText(/60%/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(onApplied).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/detections/det-1/config");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({ config: { failure_threshold: 12 } });
  });

  it("shows an error and re-enables Apply when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ error: { code: "server_error", message: "boom", details: null } }),
            { status: 500 },
          ),
      ),
    );
    const user = userEvent.setup();

    render(
      <TuningSuggestionsPanel
        suggestions={[SUGGESTION]}
        loading={false}
        detectionsByRuleKey={new Map([["ssh_brute_force", DETECTION]])}
        onApplied={() => {}}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(screen.getByText(/couldn't save/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Apply" })).not.toBeDisabled();
  });
});
