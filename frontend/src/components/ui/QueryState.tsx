import "./QueryState.css";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="query-state query-state-loading">
      <span className="query-state-spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="query-state query-state-empty">
      <span>{message}</span>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="query-state query-state-error">
      <span>{message}</span>
      {onRetry && (
        <button type="button" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}
