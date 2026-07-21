import { type Session } from "../types";
import { formatTime, dayLabel } from "../lib/format";
import {
  type Provider,
  PROVIDERS,
  PROVIDER_LABEL,
  PROVIDER_SHORT,
} from "../lib/agents";
import { Tooltip } from "./Tooltip";
import { ProviderIcon } from "./ProviderIcon";

interface Props {
  width: number;
  onWidthChange: (width: number) => void;
  sessions: Session[]; // already scoped by agentFilter — counts reflect what's actually shown
  allSessions: Session[]; // full, unscoped list — used only for per-agent session counts
  selectedSession: string | null;
  onSelectSession: (id: string | null) => void;
  agentFilter: Provider | null;
  onSelectAgent: (p: Provider | null) => void;
}

export function SessionSidebar({
  width,
  onWidthChange,
  sessions,
  allSessions,
  selectedSession,
  onSelectSession,
  agentFilter,
  onSelectAgent,
}: Props) {
  // Group sessions by day bucket, preserving order.
  const groups = new Map<string, Session[]>();
  for (const s of sessions) {
    const day = dayLabel(s.started_at);
    (groups.get(day) ?? groups.set(day, []).get(day)!).push(s);
  }

  return (
    <aside style={{ width }} className="relative flex min-w-52 max-w-[38vw] shrink-0 flex-col overflow-hidden border-r border-border bg-surface/40">
      {/* Agent scope — splits the unified timeline by which hook recorded the
          event, since Claude Code and Codex can run against the same repo at once. */}
      <div className="border-b border-border px-3 py-3">
        <SidebarHeading>Agent</SidebarHeading>
        <div className="mt-1 flex flex-wrap gap-1">
          <button
            onClick={() => onSelectAgent(null)}
            className={[
              "cursor-pointer rounded-full border px-2.5 py-1 font-mono text-[11px] transition-colors",
              agentFilter === null
                ? "border-transparent bg-surface-2 text-ink"
                : "border-border text-ink-muted hover:bg-surface/70 hover:text-ink",
            ].join(" ")}
          >
            All ({allSessions.length})
          </button>
          {PROVIDERS.map((p) => {
            const count = allSessions.filter((s) => s.provider === p).length;
            const on = agentFilter === p;
            return (
              <button
                key={p}
                onClick={() => onSelectAgent(on ? null : p)}
                className={[
                  "flex cursor-pointer items-center gap-1 rounded-full border px-2.5 py-1 font-mono text-[11px] transition-colors",
                  on
                    ? "border-transparent bg-surface-2 text-ink"
                    : "border-border text-ink-muted hover:bg-surface/70 hover:text-ink",
                ].join(" ")}
              >
                <ProviderIcon provider={p} />
                {PROVIDER_SHORT[p]} ({count})
              </button>
            );
          })}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-2 py-3">
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
                  {agentFilter === null && (
                    <Tooltip label={PROVIDER_LABEL[s.provider]} className="ml-auto shrink-0">
                      <span className="rounded bg-surface-2 px-1 py-0.5 font-mono text-[9px] uppercase text-ink-faint">
                        {PROVIDER_SHORT[s.provider]}
                      </span>
                    </Tooltip>
                  )}
                </span>
              </button>
            ))}
          </div>
        ))}
      </div>

      <div
        role="separator"
        aria-label="Resize sidebar"
        aria-orientation="vertical"
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          const startX = event.clientX;
          const startWidth = width;
          const move = (e: PointerEvent) => onWidthChange(Math.max(208, Math.min(window.innerWidth * 0.38, startWidth + e.clientX - startX)));
          const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
          window.addEventListener("pointermove", move);
          window.addEventListener("pointerup", up, { once: true });
        }}
        className="absolute inset-y-0 right-0 z-10 w-1 cursor-col-resize transition-colors hover:bg-risk-write/60"
      />
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
