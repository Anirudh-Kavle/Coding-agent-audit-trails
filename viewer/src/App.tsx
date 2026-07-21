import { useEffect, useMemo, useRef, useState } from "react";
import type { Session } from "./types";
import { dataSource } from "./lib/dataSource";
import { getUsage, getBudgets, updateScopeBudget, type BudgetSetting } from "./lib/api";
import { useEventStream } from "./hooks/useEventStream";
import { useKeyboardNav } from "./hooks/useKeyboardNav";
import { byNewest } from "./lib/format";
import { filterEvents } from "./lib/search";
import { TopBar } from "./components/TopBar";
import { SessionSidebar } from "./components/SessionSidebar";
import { Timeline } from "./components/Timeline";
import { DetailDrawer } from "./components/DetailDrawer";
import { EmptyState } from "./components/EmptyState";
import { Pagination } from "./components/Pagination";
import type { Provider } from "./lib/agents";

const PAGE_SIZE = 50;

export default function App() {
  const { events, loading, lastArrivalId } = useEventStream();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [dailyTokens, setDailyTokens] = useState(0);
  const [budgets, setBudgets] = useState<BudgetSetting[]>([]);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
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

  const live = sessions.some((s) => s.live);
  const searching = search.trim().length > 0;

  // Sessions scoped to the selected agent — drives both the sidebar list and
  // the "which session am I even allowed to pick" constraint below.
  const scopedSessions = useMemo(
    () => (agentFilter ? sessions.filter((s) => s.provider === agentFilter) : sessions),
    [sessions, agentFilter]
  );

  // Switching agent scope away from the selected session's own agent clears
  // the session selection rather than silently showing an empty timeline.
  useEffect(() => {
    if (!agentFilter || !selectedSession) return;
    if (!scopedSessions.some((s) => s.id === selectedSession)) setSelectedSession(null);
  }, [agentFilter, selectedSession, scopedSessions]);

  // Filter pipeline: agent scope → session scope → search (which now also
  // carries risk:/tool:/file:/session: qualifiers from the search bar's
  // filter panel). Newest-first.
  const visible = useMemo(() => {
    let list = events;
    if (agentFilter) list = list.filter((e) => e.provider === agentFilter);
    if (selectedSession) list = list.filter((e) => e.session_id === selectedSession);
    if (searching) list = filterEvents(list, search);
    return [...list].sort(byNewest);
  }, [events, agentFilter, selectedSession, search, searching]);

  // Changing scope (agent/session/search) invalidates the current page.
  useEffect(() => {
    setPage(1);
  }, [agentFilter, selectedSession, search]);

  const totalPages = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const paged = useMemo(
    () => visible.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE),
    [visible, currentPage]
  );

  const selectedEvent = drawerOpen
    ? events.find((e) => e.id === selectedId) ?? null
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
        live={live}
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
          agentFilter={agentFilter}
          onSelectAgent={setAgentFilter}
        />

        <main className="relative flex min-h-0 min-w-0 flex-1 flex-col">
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
