import { useEffect, useMemo, useRef, useState } from "react";
import type { FlightEvent, Session } from "./types";
import { dataSource } from "./lib/dataSource";
import { getUsage, getBudgets, updateScopeBudget, type BudgetSetting } from "./lib/api";
import { useEventStream } from "./hooks/useEventStream";
import { useKeyboardNav } from "./hooks/useKeyboardNav";
import { byNewest } from "./lib/format";
import { filterEvents, sessionTitleMap } from "./lib/search";
import { TopBar } from "./components/TopBar";
import { SessionSidebar, projectKeyOf, projectNameOf } from "./components/SessionSidebar";
import { Timeline } from "./components/Timeline";
import { DetailDrawer } from "./components/DetailDrawer";
import { EmptyState } from "./components/EmptyState";
import { SessionStatsBar } from "./components/SessionStatsBar";
import { Pagination } from "./components/Pagination";
import type { Provider } from "./lib/agents";

const PAGE_SIZE = 50;

export default function App() {
  const { events, loading, lastArrivalId } = useEventStream();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [dailyTokens, setDailyTokens] = useState(0);
  const [budgets, setBudgets] = useState<BudgetSetting[]>([]);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [sidebarWidth, setSidebarWidth] = useState(260);
  const [agentFilter, setAgentFilter] = useState<Provider | null>(null);
  const [page, setPage] = useState(1);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    dataSource.getSessions().then(setSessions);
    getUsage().then((u) => setDailyTokens(u.token_count)).catch(() => undefined);
    getBudgets().then(setBudgets).catch(() => undefined);

    // The session list (which session is "live" per provider, its token
    // usage, its provider) can change outside this tab — a new `fr api-ui`
    // terminal starting, a session ending. Without this, the budget button
    // keeps targeting whatever was live at page load, so "Save limits" can
    // silently patch a stale session instead of the one actually running.
    const id = setInterval(() => {
      dataSource.getSessions().then(setSessions);
      getBudgets().then(setBudgets).catch(() => undefined);
    }, 4000);
    return () => clearInterval(id);
  }, []);

  const searching = search.trim().length > 0;

  // Sessions scoped to the selected agent — drives the sidebar's project tree
  // and the "which session/project am I even allowed to have selected" checks
  // below.
  const scopedSessions = useMemo(
    () => (agentFilter ? sessions.filter((s) => s.provider === agentFilter) : sessions),
    [sessions, agentFilter]
  );

  // session: qualifier matches either the raw id or Claude Code's own
  // human-readable session title.
  const sessionTitles = useMemo(() => sessionTitleMap(sessions), [sessions]);

  // Switching agent scope away from whatever's selected (session, folder, or
  // project group) clears that selection rather than silently showing an
  // empty timeline.
  useEffect(() => {
    if (!agentFilter) return;
    if (selectedSession && !scopedSessions.some((s) => s.id === selectedSession)) {
      setSelectedSession(null);
    }
    if (selectedProject && !scopedSessions.some((s) => projectKeyOf(s) === selectedProject)) {
      setSelectedProject(null);
    }
    if (selectedGroup && !scopedSessions.some((s) => projectNameOf(s) === selectedGroup)) {
      setSelectedGroup(null);
    }
  }, [agentFilter, selectedSession, selectedProject, selectedGroup, scopedSessions]);

  // Full-database search: the loaded timeline holds only the newest events,
  // so an active query also asks the backend (FTS + qualifiers over every
  // session ever recorded). Debounced; the client-side filter below gives
  // instant results over loaded events until the full set arrives.
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

  // Scope hierarchy: session > folder/clone (project key) > project name
  // (all folders of that name) > everything, all within the agent scope.
  const scopeSessionIds = useMemo(() => {
    if (selectedSession) return null; // session filter handles it directly
    if (selectedProject) {
      return new Set(
        scopedSessions.filter((s) => projectKeyOf(s) === selectedProject).map((s) => s.id)
      );
    }
    if (selectedGroup) {
      return new Set(
        scopedSessions.filter((s) => projectNameOf(s) === selectedGroup).map((s) => s.id)
      );
    }
    return null;
  }, [scopedSessions, selectedSession, selectedProject, selectedGroup]);

  // Events restricted to the agent scope only — the base for both the stats
  // bar (which ignores the search box) and the searchable timeline below.
  const agentScopedEvents = useMemo(
    () => (agentFilter ? events.filter((e) => e.provider === agentFilter) : events),
    [events, agentFilter]
  );

  // Filter pipeline: agent scope → session/project scope → search (free text
  // + qualifiers, either from the backend once it answers or the client-side
  // fallback while it's in flight). Newest-first.
  const visible = useMemo(() => {
    // remoteResults comes straight from the backend, which doesn't know about
    // the agent scope — re-apply it here. A no-op when the base list is
    // already agentScopedEvents (already filtered).
    let list = searching && remoteResults ? remoteResults : agentScopedEvents;
    if (agentFilter) list = list.filter((e) => e.provider === agentFilter);
    if (selectedSession) list = list.filter((e) => e.session_id === selectedSession);
    else if (scopeSessionIds) list = list.filter((e) => scopeSessionIds.has(e.session_id));
    if (searching && !remoteResults) list = filterEvents(list, search, sessionTitles);
    return [...list].sort(byNewest);
  }, [agentScopedEvents, remoteResults, agentFilter, selectedSession, scopeSessionIds, search, searching, sessionTitles]);

  // Changing scope (agent/session/project/search) invalidates the current page.
  useEffect(() => {
    setPage(1);
  }, [agentFilter, selectedSession, selectedProject, selectedGroup, search]);

  const totalPages = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const paged = useMemo(
    () => visible.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE),
    [visible, currentPage]
  );

  // Search hits can reference events outside the loaded stream — check the
  // remote result set too.
  const selectedEvent = drawerOpen
    ? events.find((e) => e.id === selectedId) ?? remoteResults?.find((e) => e.id === selectedId) ?? null
    : null;

  const moveSelection = (delta: number) => {
    if (paged.length === 0) return;
    const idx = paged.findIndex((e) => e.id === selectedId);
    const nextIdx = Math.max(0, Math.min(paged.length - 1, (idx < 0 ? -1 : idx) + delta));
    setSelectedId(paged[nextIdx].id);
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
        search={search}
        onSearch={setSearch}
        onClearSearch={() => setSearch("")}
        sessions={scopedSessions}
        agentFilter={agentFilter}
        sessionBudget={(() => { const b = budgets.find((x) => x.scope === "openai-api"); return b?.token_limit ? { id: "openai-api", used: b.token_used, limit: b.token_limit, timeLimit: b.time_limit_s ?? undefined } : undefined; })()}
        dailyTokens={dailyTokens}
        budgets={budgets}
        onBudgetSaved={async (scope, tokenLimit, timeLimit) => {
          await updateScopeBudget(scope, tokenLimit, timeLimit);
          setBudgets((all) => all.map((b) => b.scope === scope ? { ...b, token_limit: tokenLimit, time_limit_s: timeLimit } : b));
        }}
      />

      <div className="flex min-h-0 flex-1">
        <SessionSidebar
          sessions={scopedSessions}
          allSessions={sessions}
          width={sidebarWidth}
          onWidthChange={setSidebarWidth}
          selectedSession={selectedSession}
          onSelectSession={setSelectedSession}
          selectedProject={selectedProject}
          onSelectProject={setSelectedProject}
          selectedGroup={selectedGroup}
          onSelectGroup={setSelectedGroup}
          agentFilter={agentFilter}
          onSelectAgent={setAgentFilter}
        />

        <main className="relative flex min-h-0 min-w-0 flex-1 flex-col">
          <SessionStatsBar
            selectedSession={scopedSessions.find((s) => s.id === selectedSession) ?? null}
            scopeSessions={
              scopeSessionIds ? scopedSessions.filter((s) => scopeSessionIds.has(s.id)) : scopedSessions
            }
            scopeLabel={
              selectedProject
                ? `folder ${selectedProject.replace(/[\\/]+$/, "").split(/[\\/]/).pop()}`
                : selectedGroup
                  ? `project ${selectedGroup}`
                  : `all projects`
            }
            events={
              scopeSessionIds
                ? agentScopedEvents.filter((e) => scopeSessionIds.has(e.session_id))
                : agentScopedEvents
            }
          />
          <Timeline
            key={currentPage}
            events={paged}
            loading={loading}
            selectedId={selectedId}
            lastArrivalId={currentPage === 1 ? lastArrivalId : null}
            onSelect={(id) => {
              setSelectedId(id);
              setDrawerOpen(true);
            }}
            empty={<EmptyState mode={searching ? "no-results" : "no-events"} />}
          />
          <Pagination page={currentPage} totalPages={totalPages} onChange={setPage} />
          <DetailDrawer event={selectedEvent} onClose={() => setDrawerOpen(false)} />
        </main>
      </div>
    </div>
  );
}
