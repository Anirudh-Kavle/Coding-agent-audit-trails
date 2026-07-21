import { type FlightEvent, RISK_DOT } from "../types";
import { formatTime, eventSummary, reasoningFirstLine } from "../lib/format";
import { RiskBadge } from "./RiskBadge";
import { PROVIDER_SHORT, PROVIDER_DESCRIPTION } from "../lib/agents";
import { Tooltip } from "./Tooltip";

interface Props {
  event: FlightEvent;
  selected: boolean;
  isNew: boolean; // just arrived → slide-in + (if sensitive) pulse, once
  onClick: () => void;
}

// Row anatomy (spec 4.2): risk dot · time · tool badge · one-line summary ·
// inline first-line-of-reasoning in muted italics ("↳ why: …").
export function EventRow({ event, selected, isNew, onClick }: Props) {
  const why = reasoningFirstLine(event);
  const sensitive = event.risk === "sensitive";

  return (
    <button
      onClick={onClick}
      aria-pressed={selected}
      className={[
        "group block w-full cursor-pointer border-l-2 px-4 py-2.5 text-left transition-colors",
        isNew ? "fr-slide-in" : "",
        selected
          ? "border-l-ink bg-surface-2"
          : "border-l-transparent hover:border-l-border hover:bg-surface/70",
      ].join(" ")}
    >
      <div className="flex items-center gap-3">
        <span
          className={[
            "h-2.5 w-2.5 shrink-0 rounded-full",
            RISK_DOT[event.risk],
            isNew && sensitive ? "fr-pulse" : "",
          ].join(" ")}
          aria-hidden
        />
        <time className="shrink-0 font-mono text-xs text-ink-faint">
          {formatTime(event.ts)}
        </time>
        <span className="shrink-0 rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase tracking-wide text-ink-muted">
          {event.tool}
        </span>
        <Tooltip label={PROVIDER_DESCRIPTION[event.provider]} className="shrink-0 inline-flex">
          <span className="rounded border border-border-soft px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide text-ink-faint">
            {PROVIDER_SHORT[event.provider]}
          </span>
        </Tooltip>
        <span className="min-w-0 flex-1 truncate font-mono text-sm text-ink">
          {eventSummary(event)}
        </span>
        <span className="shrink-0">
          <RiskBadge risk={event.risk} size="xs" />
        </span>
      </div>

      {(why || event.capture_gap) && (
        <p className="mt-1 truncate pl-5.5 text-xs italic">
          {why ? (
            <span className="text-ink-muted">↳ why: {why}</span>
          ) : (
            <span className="text-risk-exec">↳ reasoning unavailable</span>
          )}
        </p>
      )}
    </button>
  );
}
