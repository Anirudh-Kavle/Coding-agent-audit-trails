// The one sanctioned theatrical element: ● REC when events are flowing.
// The pulse is CSS-driven and killed by prefers-reduced-motion (see index.css).
export function RecIndicator({ live }: { live: boolean }) {
  return (
    <span className="inline-flex items-center gap-2 font-mono text-sm tracking-wide">
      <span
        className={`h-2.5 w-2.5 rounded-full ${
          live ? "bg-rec fr-rec-dot" : "bg-ink-faint"
        }`}
        aria-hidden
      />
      <span className={live ? "text-rec" : "text-ink-faint"}>
        {live ? "REC" : "IDLE"}
      </span>
    </span>
  );
}
