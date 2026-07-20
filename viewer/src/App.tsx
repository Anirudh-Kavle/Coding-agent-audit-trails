import { useEffect, useMemo, useRef, useState } from "react";
import { type FlightEvent, type RiskTier, RISK_TIERS, type Session } from "./types";
import { dataSource } from "./lib/dataSource";
import { useEventStream } from "./hooks/useEventStream";
import { useKeyboardNav } from "./hooks/useKeyboardNav";
import { byNewest } from "./lib/format";
import { filterEvents } from "./lib/search";
import { TopBar } from "./components/TopBar";
import { SessionSidebar } from "./components/SessionSidebar";
import { Timeline } from "./components/Timeline";
import { DetailDrawer } from "./components/DetailDrawer";
import { EmptyState } from "./components/EmptyState";
import { SessionStatsBar } from "./components/SessionStatsBar";
import { SessionSummaryPanel } from "./components/SessionSummary";

export default function App() {
  const { events, loading, lastArrivalId } = useEventStream();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [riskFilter, setRiskFilter] = useState<Set<RiskTier>>(new Set(RISK_TIERS));
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    dataSource.getSessions().then(setSessions);
  }, []);

  const live = sessions.some((s) => s.live);
  const searching = search.trim().length > 0;

  // Full-database search: the loaded timeline holds only the newest events,
  // so an active query also asks the backend (FTS over every session ever
  // recorded). Debounced; the client-side filter below gives instant results
  // over loaded events until the full set arrives.
  const [remoteResults, setRemoteResults] = useState<FlightEvent[] | null>(null);
  useEffect(() => {
    if (!searching) {
      setRemoteResults(null);
      return;
    }
    let stale = false;
    const timer = setTimeout(() => {
      dataSource
        .search(search)
        .then((r) => {
          if (!stale) setRemoteResults(r);
        })
        .catch(() => {
          if (!stale) setRemoteResults(null); // backend unreachable → keep client filter
        });
    }, 250);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [search, searching]);

  // Filter pipeline: session scope → risk filter → search. Newest-first for the timeline.
  const visible = useMemo(() => {
    let list = searching && remoteResults ? remoteResults : events;
    if (selectedSession) list = list.filter((e) => e.session_id === selectedSession);
    list = list.filter((e) => riskFilter.has(e.risk));
    if (searching && !remoteResults) list = filterEvents(list, search);
    return [...list].sort(byNewest);
  }, [events, remoteResults, selectedSession, riskFilter, search, searching]);

  // Search hits and summary citations can reference events outside the loaded
  // stream — check the remote result set and the citation-fetched event too.
  const [fetchedEvent, setFetchedEvent] = useState<FlightEvent | null>(null);
  const selectedEvent = drawerOpen
    ? events.find((e) => e.id === selectedId) ??
      remoteResults?.find((e) => e.id === selectedId) ??
      (fetchedEvent?.id === selectedId ? fetchedEvent : null)
    : null;

  // Summary citation click: the cited event may be anywhere in history.
  const openCitedEvent = (id: number) => {
    const local = events.find((e) => e.id === id) ?? remoteResults?.find((e) => e.id === id);
    if (local) {
      setSelectedId(id);
      setDrawerOpen(true);
      return;
    }
    dataSource.getEvent(id).then((e) => {
      if (!e) return;
      setFetchedEvent(e);
      setSelectedId(id);
      setDrawerOpen(true);
    });
  };

  const toggleRisk = (r: RiskTier) => {
    setRiskFilter((prev) => {
      const next = new Set(prev);
      if (next.has(r)) next.delete(r);
      else next.add(r);
      return next;
    });
  };

  const moveSelection = (delta: number) => {
    if (visible.length === 0) return;
    const idx = visible.findIndex((e) => e.id === selectedId);
    const nextIdx = Math.max(0, Math.min(visible.length - 1, (idx < 0 ? -1 : idx) + delta));
    setSelectedId(visible[nextIdx].id);
  };

  useKeyboardNav({
    onDown: () => moveSelection(1),
    onUp: () => moveSelection(-1),
    onOpen: () => selectedId !== null && setDrawerOpen(true),
    onSearch: () => searchRef.current?.focus(),
    onEscape: () => {
      if (drawerOpen) setDrawerOpen(false);
      else if (searching) setSearch("");
    },
  });

  return (
    <div className="flex h-full flex-col">
      <TopBar
        ref={searchRef}
        live={live}
        search={search}
        onSearch={setSearch}
        onClearSearch={() => setSearch("")}
      />

      <div className="flex min-h-0 flex-1">
        <SessionSidebar
          sessions={sessions}
          selectedSession={selectedSession}
          onSelectSession={setSelectedSession}
          riskFilter={riskFilter}
          onToggleRisk={toggleRisk}
        />

        <main className="relative flex min-h-0 min-w-0 flex-1 flex-col">
          <SessionStatsBar
            selectedSession={sessions.find((s) => s.id === selectedSession) ?? null}
            sessions={sessions}
            events={events}
          />
          {selectedSession && (
            <SessionSummaryPanel sessionId={selectedSession} onOpenEvent={openCitedEvent} />
          )}
          <Timeline
            events={visible}
            loading={loading}
            selectedId={selectedId}
            lastArrivalId={lastArrivalId}
            onSelect={(id) => {
              setSelectedId(id);
              setDrawerOpen(true);
            }}
            empty={<EmptyState mode={searching ? "no-results" : "no-events"} />}
          />
          <DetailDrawer event={selectedEvent} onClose={() => setDrawerOpen(false)} />
        </main>
      </div>
    </div>
  );
}
