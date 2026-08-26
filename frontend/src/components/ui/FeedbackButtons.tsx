import { useState } from "react";
import { clearAnalysisFeedback, setAnalysisFeedback } from "../../api/resources";
import type { FeedbackRating } from "../../api/types";
import "./FeedbackButtons.css";

/** Thumbs up/down on one AnalysisResult — the first mutating action in
 * this dashboard. Optimistic: the UI updates immediately and rolls back
 * only if the request actually fails, since a vote is low-stakes and the
 * common case (success) shouldn't feel any slower than a static badge.
 * See DEF.md § Phase 9, "Analysis feedback (post-roadmap)".
 */
export function FeedbackButtons({
  analysisResultId,
  initialRating,
}: {
  analysisResultId: string;
  initialRating: FeedbackRating | null;
}) {
  const [rating, setRating] = useState<FeedbackRating | null>(initialRating);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(false);

  async function vote(next: FeedbackRating) {
    if (pending) return;
    const previous = rating;
    const clearing = previous === next;
    setError(false);
    setPending(true);
    setRating(clearing ? null : next);
    try {
      if (clearing) {
        await clearAnalysisFeedback(analysisResultId);
      } else {
        await setAnalysisFeedback(analysisResultId, next);
      }
    } catch {
      setRating(previous);
      setError(true);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="feedback-buttons" aria-label="Was this AI analysis useful?">
      <button
        type="button"
        className="feedback-button"
        data-active={rating === "up"}
        disabled={pending}
        aria-pressed={rating === "up"}
        aria-label="Mark this analysis as useful"
        onClick={() => void vote("up")}
      >
        ▲
      </button>
      <button
        type="button"
        className="feedback-button"
        data-active={rating === "down"}
        disabled={pending}
        aria-pressed={rating === "down"}
        aria-label="Mark this analysis as not useful"
        onClick={() => void vote("down")}
      >
        ▼
      </button>
      {error && <span className="feedback-error">couldn't save — try again</span>}
    </div>
  );
}
