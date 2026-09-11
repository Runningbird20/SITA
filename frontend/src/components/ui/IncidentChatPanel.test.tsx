import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as resources from "../../api/resources";
import type { ChatMessage } from "../../api/types";
import { IncidentChatPanel } from "./IncidentChatPanel";

afterEach(() => {
  vi.restoreAllMocks();
});

const REPLY: ChatMessage = {
  id: "msg-2",
  incident_id: "inc-1",
  role: "assistant",
  content: "This looks like a brute-force attempt from 198.51.100.1.",
  provider: "mock",
  model: "test-model",
  prompt_version: "triage-chat-v1",
  validation_status: "valid",
  confidence: 0.85,
  latency_ms: 12,
  created_at: "2026-01-15T03:00:05Z",
};

describe("IncidentChatPanel", () => {
  it("shows a loading state before history arrives", () => {
    vi.spyOn(resources, "fetchIncidentChat").mockReturnValue(new Promise(() => {}));
    render(<IncidentChatPanel incidentId="inc-1" />);
    expect(screen.getByText(/loading conversation/i)).toBeInTheDocument();
  });

  it("shows an empty-conversation hint when there's no history yet", async () => {
    vi.spyOn(resources, "fetchIncidentChat").mockResolvedValue([]);
    render(<IncidentChatPanel incidentId="inc-1" />);
    await waitFor(() => expect(screen.getByText(/ask a follow-up question/i)).toBeInTheDocument());
  });

  it("renders existing history with the analyst's question and the AI-labeled answer", async () => {
    vi.spyOn(resources, "fetchIncidentChat").mockResolvedValue([
      { ...REPLY, id: "msg-1", role: "user", content: "What happened here?" },
      REPLY,
    ]);
    render(<IncidentChatPanel incidentId="inc-1" />);

    await waitFor(() => expect(screen.getByText(/what happened here/i)).toBeInTheDocument());
    expect(screen.getByText(/brute-force attempt/i)).toBeInTheDocument();
    expect(screen.getByText("AI-generated")).toBeInTheDocument();
  });

  it("sending a question posts it and appends the reply", async () => {
    vi.spyOn(resources, "fetchIncidentChat").mockResolvedValue([]);
    const postSpy = vi.spyOn(resources, "postIncidentChatMessage").mockResolvedValue(REPLY);
    const user = userEvent.setup();

    render(<IncidentChatPanel incidentId="inc-1" />);
    await waitFor(() => expect(screen.getByPlaceholderText(/ask a question/i)).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText(/ask a question/i), "Is this a brute force?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(screen.getByText(/is this a brute force/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/brute-force attempt/i)).toBeInTheDocument());
    expect(postSpy).toHaveBeenCalledWith("inc-1", "Is this a brute force?");
  });

  it("rolls back the optimistic question and shows an error on failure", async () => {
    vi.spyOn(resources, "fetchIncidentChat").mockResolvedValue([]);
    vi.spyOn(resources, "postIncidentChatMessage").mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();

    render(<IncidentChatPanel incidentId="inc-1" />);
    await waitFor(() => expect(screen.getByPlaceholderText(/ask a question/i)).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText(/ask a question/i), "Anyone home?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(screen.getByText(/couldn't get a reply/i)).toBeInTheDocument());
    expect(screen.queryByText(/you:/i)).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText(/ask a question/i)).toHaveValue("Anyone home?");
  });
});
