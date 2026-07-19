import { useEffect, useRef, useState } from "react";
import type { FlightEvent } from "../types";
import { dataSource } from "../lib/dataSource";

// Loads the full event history once, then appends live events from the data source.
// Returns all events (newest-first ordering is applied by the Timeline) plus the id
// of the most recent arrival so rows can fire their one-time slide-in / pulse.
export function useEventStream() {
  const [events, setEvents] = useState<FlightEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastArrivalId, setLastArrivalId] = useState<number | null>(null);
  const seen = useRef<Set<number>>(new Set());

  useEffect(() => {
    let active = true;

    dataSource.getEvents().then((initial) => {
      if (!active) return;
      initial.forEach((e) => seen.current.add(e.id));
      setEvents(initial);
      setLoading(false);
    });

    const unsubscribe = dataSource.subscribe((e) => {
      if (!active || seen.current.has(e.id)) return;
      seen.current.add(e.id);
      setEvents((prev) => [...prev, e]);
      setLastArrivalId(e.id);
    });

    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  return { events, loading, lastArrivalId };
}
