import type { FlightEvent, Session, SessionStats } from "../types";

interface Props {
  selectedSession: Session | null; // null = all sessions
  sessions: Session[];
  events: FlightEvent[]; // fallback source when backend stats are absent (mock mode)
}

const EDIT_TOOLS = ["edit", "write", "notebookedit", "apply_patch", "write_file"];
const BASH_TOOLS = ["bash", "run_command"];

// Mock-mode fallback: derive the same counts from whatever events are loaded.
function statsFromEvents(events: FlightEvent[]): SessionStats {
  const s: SessionStats = {
    action_count: 0,
    edit_count: 0,
    bash_count: 0,
    failed_count: 0,
    sensitive_count: 0,
  };
  for (const e of events) {
    if (!e.tool) continue;
    s.action_count++;
    const tool = e.tool.toLowerCase();
    if (EDIT_TOOLS.includes(tool)) s.edit_count++;
    if (BASH_TOOLS.includes(tool)) s.bash_count++;
    if (!e.exit_ok) s.failed_count++;
    if (e.risk === "sensitive") s.sensitive_count++;
    if (!s.git_branch && e.git_branch) s.git_branch = e.git_branch;
  }
  return s;
}

function sumStats(sessions: Session[]): SessionStats | null {
  const withStats = sessions.filter((s) => s.stats);
  if (withStats.length === 0) return null;
  const total: SessionStats = {
    action_count: 0,
    edit_count: 0,
    bash_count: 0,
    failed_count: 0,
    sensitive_count: 0,
  };
  for (const { stats } of withStats) {
    total.action_count += stats!.action_count;
    total.edit_count += stats!.edit_count;
    total.bash_count += stats!.bash_count;
    total.failed_count += stats!.failed_count;
    total.sensitive_count += stats!.sensitive_count;
  }
  return total;
}

function Stat({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  return (
    <span className={`whitespace-nowrap ${tone ?? "text-ink-muted"}`}>
      <span className="font-semibold text-ink">{value}</span> {label}
    </span>
  );
}

// Deterministic session summary — plain counts straight from the store, no
// inference. The instant "what did this session do?" line above the timeline.
export function SessionStatsBar({ selectedSession, sessions, events }: Props) {
  const scopeEvents = selectedSession
    ? events.filter((e) => e.session_id === selectedSession.id)
    : events;
  const stats = selectedSession
    ? selectedSession.stats ?? statsFromEvents(scopeEvents)
    : sumStats(sessions) ?? statsFromEvents(scopeEvents);

  if (stats.action_count === 0) return null;

  const scope = selectedSession
    ? `session ${selectedSession.id.slice(0, 8)}`
    : `all sessions (${sessions.length})`;

  return (
    <div
      className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-border bg-surface px-4 py-2 font-mono text-xs"
      data-testid="session-stats"
    >
      <span className="uppercase tracking-wide text-ink-faint">{scope}</span>
      <Stat label="actions" value={stats.action_count} />
      <Stat label="commands" value={stats.bash_count} />
      <Stat label="edits" value={stats.edit_count} />
      {stats.failed_count > 0 && (
        <Stat label="failed" value={stats.failed_count} tone="text-risk-exec" />
      )}
      {stats.sensitive_count > 0 && (
        <Stat label="sensitive" value={stats.sensitive_count} tone="text-risk-sensitive" />
      )}
      {stats.git_branch && <Stat label="" value={`⎇ ${stats.git_branch}`} />}
    </div>
  );
}
