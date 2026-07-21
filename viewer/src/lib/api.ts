import type { FlightEvent, Session } from "../types";
import { RISK_TIERS } from "../types";
import type { Provider } from "./agents";

const API_BASE = import.meta.env.VITE_API_URL || "/api";

// --- Wire types: what the FastAPI backend actually returns (raw SQLite rows,
// except risk_reasons which the server deserializes to a list). ---

interface RawEvent {
  id: number;
  session_id: string;
  ts: number;
  phase: string;
  tool: string;
  provider: string | null;
  arguments_json: string | null;
  result_json: string | null;
  exit_ok: 0 | 1 | null;
  reasoning_text: string | null;
  risk: string;
  risk_reasons: string[] | string | null;
  capture_gap: 0 | 1;
  git_branch: string | null;
  git_head: string | null;
  git_dirty: 0 | 1 | null;
  files_touched: string | null;
}

interface RawSession {
  id: string;
  started_at: number;
  ended_at: number | null;
  cwd: string;
  git_repo: string | null;
  source: string | null;
  title: string | null;
  action_count?: number;
  edit_count?: number;
  bash_count?: number;
  failed_count?: number;
  sensitive_count?: number;
  git_branch?: string | null;
  project_key?: string;
  project?: string;
  token_limit?: number | null;
  token_used?: number | null;
  time_limit_s?: number | null;
  provider?: string | null;
}

const KNOWN_PROVIDERS = new Set<string>(["claude", "codex", "openai-api"]);
function normalizeProvider(raw: string | null | undefined): Provider {
  return raw && KNOWN_PROVIDERS.has(raw) ? (raw as Provider) : "unknown";
}

// Parse a JSON-string column without ever throwing. The hook truncates
// payloads at 16KB with a "...[truncated]" suffix, which breaks JSON.parse —
// fall back to wrapping the raw string so the drawer can still show it.
function looseJson(s: string | null | undefined): Record<string, unknown> | undefined {
  if (!s) return undefined;
  try {
    const parsed: unknown = JSON.parse(s);
    if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
    return { raw: s };
  } catch {
    return { raw: s };
  }
}

export function normalizeEvent(raw: RawEvent): FlightEvent {
  let files: string[] = [];
  if (raw.files_touched) {
    try {
      const parsed: unknown = JSON.parse(raw.files_touched);
      if (Array.isArray(parsed)) files = parsed.map(String);
    } catch {
      // garbage in the column → no files
    }
  }

  const reasons = Array.isArray(raw.risk_reasons)
    ? raw.risk_reasons.join("; ")
    : (raw.risk_reasons ?? "");

  return {
    id: raw.id,
    session_id: raw.session_id,
    ts: raw.ts,
    phase: raw.phase as FlightEvent["phase"],
    tool: raw.tool,
    provider: normalizeProvider(raw.provider),
    arguments_json: looseJson(raw.arguments_json) ?? {},
    result_json: looseJson(raw.result_json),
    exit_ok: raw.exit_ok === null ? null : raw.exit_ok === 1,
    risk: (RISK_TIERS as string[]).includes(raw.risk) ? (raw.risk as FlightEvent["risk"]) : "info",
    risk_reasons: reasons || undefined,
    reasoning_text: raw.reasoning_text ?? undefined,
    capture_gap: raw.capture_gap === 1,
    git_branch: raw.git_branch ?? undefined,
    git_head: raw.git_head ?? undefined,
    git_dirty: raw.git_dirty === null ? null : raw.git_dirty === 1,
    files_touched: files,
    created_at: raw.ts,
  };
}

// Claude Code's SessionStart sends source ∈ {startup, resume, clear, compact};
// map onto the viewer's union. Everything non-resume is an interactive session.
const SOURCE_MAP: Record<string, Session["source"]> = {
  startup: "interactive",
  resume: "resumed",
  clear: "interactive",
  compact: "interactive",
};

export function normalizeSession(raw: RawSession): Session {
  return {
    id: raw.id,
    started_at: raw.started_at,
    ended_at: raw.ended_at ?? undefined,
    cwd: raw.cwd,
    git_repo: raw.git_repo ?? undefined,
    source: SOURCE_MAP[raw.source ?? ""] ?? "interactive",
    provider: normalizeProvider(raw.provider),
    label: raw.title ?? undefined,
    live: raw.ended_at == null,
    project_key: raw.project_key,
    project: raw.project,
    token_limit: raw.token_limit ?? undefined,
    token_used: raw.token_used ?? undefined,
    time_limit_s: raw.time_limit_s ?? undefined,
    stats:
      raw.action_count != null
        ? {
            action_count: raw.action_count,
            edit_count: raw.edit_count ?? 0,
            bash_count: raw.bash_count ?? 0,
            failed_count: raw.failed_count ?? 0,
            sensitive_count: raw.sensitive_count ?? 0,
            git_branch: raw.git_branch ?? undefined,
          }
        : undefined,
  };
}

export async function getUsage(): Promise<{ token_count: number }> {
  const res = await fetch(`${API_BASE}/usage`);
  if (!res.ok) throw new Error("Failed to fetch usage");
  return res.json();
}

export async function updateBudget(sessionId: string, tokenLimit: number | null, timeLimit: number | null) {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/budget`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token_limit: tokenLimit, time_limit_s: timeLimit }),
  });
  if (!res.ok) throw new Error("Could not update session limits");
  return res.json();
}

// --- Fetchers ---

export async function getSessions(): Promise<Session[]> {
  const res = await fetch(`${API_BASE}/sessions`);
  if (!res.ok) throw new Error("Failed to fetch sessions");
  const raw: RawSession[] = await res.json();
  return raw.map(normalizeSession);
}

export async function getEvents(
  sessionId?: string,
  filter?: Record<string, string>
): Promise<FlightEvent[]> {
  const qs = filter ? "?" + new URLSearchParams(filter).toString() : "";
  const res = await fetch(`${API_BASE}/sessions/${sessionId || "all"}/events${qs}`);
  if (!res.ok) throw new Error("Failed to fetch events");
  const raw: RawEvent[] = await res.json();
  return raw.map(normalizeEvent);
}

export async function search(query: string): Promise<FlightEvent[]> {
  const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error("Failed to search");
  const raw: RawEvent[] = await res.json();
  return raw.map(normalizeEvent);
}

export async function getRecordingPaused(): Promise<boolean> {
  const res = await fetch(`${API_BASE}/recording`);
  if (!res.ok) throw new Error("Failed to fetch recording status");
  const data: { paused: boolean } = await res.json();
  return data.paused;
}

export async function setRecordingPaused(paused: boolean): Promise<boolean> {
  const res = await fetch(`${API_BASE}/recording/${paused ? "pause" : "resume"}`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to update recording status");
  const data: { paused: boolean } = await res.json();
  return data.paused;
}

export function streamEvents(
  onEvent: (event: FlightEvent) => void,
  onError?: (error: Error) => void
): () => void {
  const eventSource = new EventSource(`${API_BASE}/stream`);

  eventSource.onmessage = (e) => {
    try {
      const raw: RawEvent = JSON.parse(e.data);
      onEvent(normalizeEvent(raw));
    } catch (err) {
      onError?.(err as Error);
    }
  };

  eventSource.onerror = () => {
    onError?.(new Error("SSE connection failed"));
    eventSource.close();
  };

  return () => eventSource.close();
}
