import { useState } from "react";
import { type FlightEvent, RISK_DOT, RISK_TIERS } from "../types";
import { formatTime } from "../lib/format";
import { summarizeGroup } from "../lib/groupEvents";
import { RiskBadge } from "./RiskBadge";
import { PROVIDER_SHORT, PROVIDER_DESCRIPTION } from "../lib/agents";
import { Tooltip } from "./Tooltip";
import { EventRow } from "./EventRow";

interface Props {
  events: FlightEvent[]; // 2+, newest-first, same session, same turn (or same kind+time-window)
  selectedId: number | null;
  lastArrivalId: number | null;
  onSelect: (id: number) => void;
}

function worstRisk(events: FlightEvent[]) {
  return events.reduce(
    (worst, e) => (RISK_TIERS.indexOf(e.risk) > RISK_TIERS.indexOf(worst) ? e.risk : worst),
    events[0].risk
  );
}

// A collapsed stand-in for everything a single prompt/turn did (or, for
// older data with no recorded turn_id, a same-kind burst within a session) —
// the goal is to show *what the agent was doing* at a glance, not just hide
// duplicates. Collapsed, it's one summary row; expanded, it reveals every
// real event underneath, still individually selectable. risk:sensitive
// events never appear here — they're never grouped in the first place (see
// groupConsecutive).
export function EventGroupRow({ events, selectedId, lastArrivalId, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const head = events[0];
  const tail = events[events.length - 1];
  const risk = worstRisk(events);
  const containsNew = events.some((e) => e.id === lastArrivalId);
  const { badge, label, preview } = summarizeGroup(events);

  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className={[
          "block w-full cursor-pointer border-l-2 px-4 py-2.5 text-left transition-colors",
          containsNew ? "fr-slide-in" : "",
          open ? "border-l-ink bg-surface-2" : "border-l-transparent hover:border-l-border hover:bg-surface/70",
        ].join(" ")}
      >
        <div className="flex items-center gap-3">
          <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${RISK_DOT[risk]}`} aria-hidden />
          <time className="shrink-0 font-mono text-xs text-ink-faint">
            {formatTime(tail.ts)}–{formatTime(head.ts)}
          </time>
          <span className="shrink-0 rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase tracking-wide text-ink-muted">
            {badge}
          </span>
          <Tooltip label={PROVIDER_DESCRIPTION[head.provider]} className="shrink-0 inline-flex">
            <span className="rounded border border-border-soft px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide text-ink-faint">
              {PROVIDER_SHORT[head.provider]}
            </span>
          </Tooltip>
          <span className="min-w-0 flex-1 truncate font-mono text-sm text-ink">{label}</span>
          <span className="shrink-0">
            <RiskBadge risk={risk} size="xs" />
          </span>
          <span className={`shrink-0 text-ink-faint transition-transform ${open ? "rotate-90" : ""}`} aria-hidden>
            ›
          </span>
        </div>
        {preview && <p className="mt-1 truncate pl-5.5 text-xs italic text-ink-muted">↳ {preview}</p>}
      </button>

      {open && (
        <div className="divide-y divide-border-soft border-l-2 border-l-border-soft bg-surface/30 pl-3">
          {events.map((e) => (
            <EventRow
              key={e.id}
              event={e}
              selected={e.id === selectedId}
              isNew={e.id === lastArrivalId}
              onClick={() => onSelect(e.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
