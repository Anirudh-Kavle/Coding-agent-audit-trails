// Loading placeholder rows — reserves space to avoid content jump.
export function Skeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div aria-hidden className="motion-safe:animate-pulse">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-3">
          <span className="h-2.5 w-2.5 rounded-full bg-surface-2" />
          <span className="h-3 w-16 rounded bg-surface-2" />
          <span className="h-3 w-12 rounded bg-surface-2" />
          <span className="h-3 flex-1 rounded bg-surface-2" />
        </div>
      ))}
    </div>
  );
}
