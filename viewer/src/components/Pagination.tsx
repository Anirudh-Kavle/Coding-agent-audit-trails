interface Props {
  page: number; // 1-indexed
  totalPages: number;
  onChange: (page: number) => void;
}

// Windowed page-number list: 1, …, current-1, current, current+1, …, last.
function pageWindow(page: number, totalPages: number): (number | "gap")[] {
  const pages: (number | "gap")[] = [];
  const add = (p: number) => pages.push(p);

  const start = Math.max(2, page - 1);
  const end = Math.min(totalPages - 1, page + 1);

  add(1);
  if (start > 2) pages.push("gap");
  for (let p = start; p <= end; p++) add(p);
  if (end < totalPages - 1) pages.push("gap");
  if (totalPages > 1) add(totalPages);

  return pages;
}

export function Pagination({ page, totalPages, onChange }: Props) {
  if (totalPages <= 1) return null;

  return (
    <div className="flex items-center justify-center gap-1 border-t border-border-soft bg-surface/60 px-3 py-2 font-mono text-xs text-ink-muted">
      <button
        type="button"
        onClick={() => onChange(page - 1)}
        disabled={page <= 1}
        className="rounded px-2 py-1 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-30"
      >
        ‹ Prev
      </button>

      {pageWindow(page, totalPages).map((p, i) =>
        p === "gap" ? (
          <span key={`gap-${i}`} className="px-1 text-ink-faint">
            …
          </span>
        ) : (
          <button
            key={p}
            type="button"
            onClick={() => onChange(p)}
            aria-current={p === page ? "page" : undefined}
            className={
              p === page
                ? "rounded bg-risk-write/20 px-2.5 py-1 text-ink"
                : "rounded px-2.5 py-1 hover:bg-white/10"
            }
          >
            {p}
          </button>
        )
      )}

      <button
        type="button"
        onClick={() => onChange(page + 1)}
        disabled={page >= totalPages}
        className="rounded px-2 py-1 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-30"
      >
        Next ›
      </button>
    </div>
  );
}
