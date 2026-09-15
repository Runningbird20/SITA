import { useState } from "react";
import { fetchIncidentChat, postIncidentChatMessage } from "../../api/resources";
import type { ChatMessage } from "../../api/types";
import { useApiQuery } from "../../hooks/useApiQuery";
import { AiBadge } from "./Badges";
import { ErrorState, LoadingState } from "./QueryState";

/** A conversational follow-up on one incident — resolves WHATNEXT.md's
 * "Bigger bets" item, "a conversational interface with an incident". See
 * DEF.md § Phase 7, "Post-roadmap addition: a conversational interface
 * with an incident". No true token-level streaming (the backend's
 * LLMProvider.generate() returns one complete response per call, not a
 * stream) — a question is sent, then the whole reply appears at once,
 * same shape as every other AI panel on this page.
 */
export function IncidentChatPanel({ incidentId }: { incidentId: string }) {
  const query = useApiQuery(() => fetchIncidentChat(incidentId), [incidentId]);
  const [pending, setPending] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState(false);

  async function send() {
    const question = draft.trim();
    if (!question || sending) return;
    setSendError(false);
    setSending(true);
    const optimisticUser: ChatMessage = {
      id: `pending-${Date.now()}`,
      incident_id: incidentId,
      role: "user",
      content: question,
      provider: null,
      model: null,
      prompt_version: null,
      validation_status: null,
      confidence: null,
      latency_ms: null,
      created_at: new Date().toISOString(),
    };
    setPending((prev) => [...prev, optimisticUser]);
    setDraft("");
    try {
      const reply = await postIncidentChatMessage(incidentId, question);
      setPending((prev) => [...prev, reply]);
    } catch {
      setPending((prev) => prev.filter((m) => m.id !== optimisticUser.id));
      setDraft(question);
      setSendError(true);
    } finally {
      setSending(false);
    }
  }

  if (query.loading) return <LoadingState label="Loading conversation…" />;
  if (query.error) return <ErrorState message={query.error} onRetry={query.refetch} />;

  const messages = [...(query.data ?? []), ...pending];

  return (
    <div>
      {messages.length === 0 && (
        <p style={{ color: "var(--color-text-dim)", fontSize: "0.85rem" }}>
          Ask a follow-up question about this incident — answers are grounded only in the data shown
          on this page.
        </p>
      )}
      {messages.map((message) => (
        <div
          key={message.id}
          className={message.role === "assistant" ? "ai-panel" : undefined}
          style={
            message.role === "user"
              ? { padding: "0.6rem 0.9rem", marginBottom: "0.5rem" }
              : undefined
          }
        >
          {message.role === "assistant" && (
            <div className="ai-panel-header">
              <span className="ai-panel-title">Answer</span>
              <AiBadge />
            </div>
          )}
          {message.role === "user" ? (
            <div style={{ fontSize: "0.88rem" }}>
              <strong>You:</strong> {message.content}
            </div>
          ) : (
            <div className="ai-panel-body">{message.content}</div>
          )}
        </div>
      ))}

      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
        <textarea
          value={draft}
          disabled={sending}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder="Ask a question about this incident…"
          rows={2}
          style={{ flex: 1, resize: "vertical", fontFamily: "inherit", padding: "0.5rem" }}
        />
        <button type="button" disabled={sending || !draft.trim()} onClick={() => void send()}>
          {sending ? "Asking…" : "Ask"}
        </button>
      </div>
      {sendError && (
        <p style={{ color: "var(--color-red)", fontSize: "0.8rem", marginTop: "0.4rem" }}>
          Couldn't get a reply — try again.
        </p>
      )}
    </div>
  );
}
