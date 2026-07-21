import { useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { FlightEvent } from "../types";
import { EventRow } from "./EventRow";
import { EventGroupRow } from "./EventGroupRow";
import { groupConsecutive } from "../lib/groupEvents";
import { Skeleton } from "./Skeleton";

interface Props {
  events: FlightEvent[]; // newest-first
  loading: boolean;
  selectedId: number | null;
  lastArrivalId: number | null;
  onSelect: (id: number) => void;
  empty: ReactNode; // shown when not loading and no events
}

const AT_TOP = 8; // px tolerance for "still live at the top"

// Vertical stream, newest at top. Auto-scroll pauses the instant the user scrolls
// away from the top; a "paused — N new" pill returns them to live (spec 4.2).
export function Timeline({ events, loading, selectedId, lastArrivalId, onSelect, empty }: Props) {
  const groups = useMemo(() => groupConsecutive(events), [events]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const prevLen = useRef(events.length);
  const prevScrollH = useRef(0);
  const [paused, setPaused] = useState(false);
  const [newCount, setNewCount] = useState(0);

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const added = events.length - prevLen.current;

    if (added > 0) {
      if (paused) {
        // Keep the viewport stable: content grew at the top, so push scroll down by the delta.
        el.scrollTop += el.scrollHeight - prevScrollH.current;
        setNewCount((c) => c + added);
      } else {
        el.scrollTop = 0; // stay live at newest
      }
    }
    prevLen.current = events.length;
    prevScrollH.current = el.scrollHeight;
  }, [events.length, paused]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollTop <= AT_TOP) {
      if (paused) setPaused(false);
      if (newCount) setNewCount(0);
    } else if (!paused) {
      setPaused(true);
    }
  };

  const backToLive = () => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: 0, behavior: "smooth" });
    setPaused(false);
    setNewCount(0);
  };

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      {paused && newCount > 0 && (
        <button
          onClick={backToLive}
          className="fr-slide-in absolute left-1/2 top-3 z-10 -translate-x-1/2 cursor-pointer rounded-full border border-border bg-surface-2 px-3 py-1 font-mono text-xs text-ink shadow-lg transition-colors hover:border-rec"
        >
          ⏸ paused — {newCount} new ↑
        </button>
      )}

      <div ref={scrollRef} onScroll={onScroll} className="min-h-0 flex-1 divide-y divide-border-soft overflow-y-auto">
        {loading ? (
          <Skeleton rows={6} />
        ) : events.length === 0 ? (
          empty
        ) : (
          groups.map((g) =>
            g.events.length === 1 ? (
              <EventRow
                key={g.key}
                event={g.events[0]}
                selected={g.events[0].id === selectedId}
                isNew={g.events[0].id === lastArrivalId}
                onClick={() => onSelect(g.events[0].id)}
              />
            ) : (
              <EventGroupRow
                key={g.key}
                events={g.events}
                selectedId={selectedId}
                lastArrivalId={lastArrivalId}
                onSelect={onSelect}
              />
            )
          )
        )}
      </div>
    </div>
  );
}
