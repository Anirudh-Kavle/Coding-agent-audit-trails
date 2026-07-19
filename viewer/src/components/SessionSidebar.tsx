import { type Session, type RiskTier, RISK_TIERS, RISK_DOT, RISK_LABEL } from "../types";
import { formatTime, dayLabel } from "../lib/format";

interface Props {
  sessions: Session[];
  selectedSession: string | null;
  onSelectSession: (id: string | null) => void;
  riskFilter: Set<RiskTier>;
  onToggleRisk: (r: RiskTier) => void;
}

export function SessionSidebar({
  sessions,
  selectedSession,
  onSelectSession,
  riskFilter,
  onToggleRisk,
}: Props) {
  // Group sessions by day bucket, preserving order.
  const groups = new Map<string, Session[]>();
  for (const s of sessions) {
    const day = dayLabel(s.started_at);
    (groups.get(day) ?? groups.set(day, []).get(day)!).push(s);
  }

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-surface/40">
      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-3">
        <SidebarHeading>Sessions</SidebarHeading>
        <button
          onClick={() => onSelectSession(null)}
          className={[
            "mb-2 block w-full cursor-pointer rounded px-2 py-1.5 text-left text-xs transition-colors",
            selectedSession === null
              ? "bg-surface-2 text-ink"
              : "text-ink-muted hover:bg-surface/70 hover:text-ink",
          ].join(" ")}
        >
          All sessions
        </button>

        {[...groups.entries()].map(([day, list]) => (
          <div key={day} className="mb-3">
            <p className="px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-ink-faint">
              {day}
            </p>
            {list.map((s) => (
              <button
                key={s.id}
                onClick={() => onSelectSession(s.id)}
                className={[
                  "block w-full cursor-pointer rounded px-2 py-1.5 text-left transition-colors",
                  selectedSession === s.id
                    ? "bg-surface-2"
                    : "hover:bg-surface/70",
                ].join(" ")}
              >
                <span className="flex items-center gap-2">
                  <span
                    className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                      s.live ? "bg-rec fr-rec-dot" : "bg-ink-faint"
                    }`}
                    aria-hidden
                  />
                  <span className="font-mono text-xs text-ink-faint">{formatTime(s.started_at)}</span>
                  <span className="truncate text-xs text-ink">{s.label ?? s.id}</span>
                </span>
              </button>
            ))}
          </div>
        ))}
      </div>

      {/* Risk filters */}
      <div className="border-t border-border px-3 py-3">
        <SidebarHeading>Filters</SidebarHeading>
        <div className="mt-1 space-y-1">
          {RISK_TIERS.map((r) => {
            const on = riskFilter.has(r);
            return (
              <label
                key={r}
                className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-xs transition-colors hover:bg-surface/70"
              >
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() => onToggleRisk(r)}
                  className="peer sr-only"
                />
                <span
                  className={[
                    "flex h-3.5 w-3.5 items-center justify-center rounded-sm border",
                    on ? "border-transparent" : "border-border",
                    on ? RISK_DOT[r] : "",
                  ].join(" ")}
                  aria-hidden
                >
                  {on && (
                    <svg className="h-2.5 w-2.5 text-bg" viewBox="0 0 24 24" fill="none">
                      <path d="M5 12l5 5L20 7" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </span>
                <span className={on ? "text-ink" : "text-ink-muted"}>{RISK_LABEL[r]}</span>
              </label>
            );
          })}
        </div>
      </div>
    </aside>
  );
}

function SidebarHeading({ children }: { children: React.ReactNode }) {
  return (
    <p className="px-2 pb-1 font-mono text-[10px] uppercase tracking-wider text-ink-faint">
      {children}
    </p>
  );
}
