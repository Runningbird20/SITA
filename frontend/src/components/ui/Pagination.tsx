interface PaginationProps {
  total: number;
  limit: number;
  offset: number;
  onOffsetChange: (offset: number) => void;
}

export function Pagination({ total, limit, offset, onOffsetChange }: PaginationProps) {
  if (total === 0) return null;
  const from = offset + 1;
  const to = Math.min(offset + limit, total);

  return (
    <div className="pagination-bar">
      <span>
        {from}–{to} of {total}
      </span>
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <button
          type="button"
          disabled={offset === 0}
          onClick={() => onOffsetChange(Math.max(0, offset - limit))}
        >
          Previous
        </button>
        <button type="button" disabled={to >= total} onClick={() => onOffsetChange(offset + limit)}>
          Next
        </button>
      </div>
    </div>
  );
}
