// Flight Recorder event types — mirror of the SQLite `events` row (spec 3.3).
export type RiskTier = "info" | "write" | "exec" | "network" | "sensitive";

export interface FlightEvent {
  id: number;
  session_id: string;
  ts: number; // ms epoch
  phase: "pre" | "post" | "compact" | "session";
  tool: string;
  arguments_json: Record<string, unknown>;
  result_json?: Record<string, unknown>;
  exit_ok: boolean;
  risk: RiskTier;
  risk_reasons?: string;
  reasoning_text?: string;
  capture_gap: boolean;
  git_branch?: string;
  git_head?: string;
  git_dirty: boolean;
  files_touched?: string[];
  created_at: number;
}

// Deterministic per-session counts computed by SQL on the backend.
// Absent in mock mode, where the UI derives them from loaded events instead.
export interface SessionStats {
  action_count: number;
  edit_count: number;
  bash_count: number;
  failed_count: number;
  sensitive_count: number;
  git_branch?: string;
}

// Local-LLM prose summary cached in sessions.summary. Citations in `text`
// look like "[event 123]" and are validated server-side against real rows.
export interface SessionSummary {
  text: string;
  model?: string | null;
  generated_at?: number | null;
  legacy?: boolean; // pre-citation-pipeline summary of unknown provenance
}

export interface SummaryResponse {
  summary: SessionSummary | null;
  available: boolean; // whether this install can generate (model present)
  error?: string;
}

export interface Session {
  id: string;
  started_at: number;
  ended_at?: number;
  cwd: string;
  git_repo?: string;
  source: "interactive" | "headless" | "resumed";
  label?: string; // human-friendly name for the sidebar
  live?: boolean; // currently recording
  stats?: SessionStats;
  // Derived project identity: repo root when in git, else the working folder.
  project_key?: string; // full path — the grouping key
  project?: string; // folder/repo basename — the display name
  last_event_ts?: number; // for summary staleness checks
}

export const RISK_TIERS: RiskTier[] = [
  "info",
  "write",
  "exec",
  "network",
  "sensitive",
];

export const RISK_LABEL: Record<RiskTier, string> = {
  info: "info",
  write: "write",
  exec: "exec",
  network: "network",
  sensitive: "sensitive",
};

// Semantic token classes (defined in index.css @theme). Color is never the only signal.
export const RISK_DOT: Record<RiskTier, string> = {
  info: "bg-risk-info",
  write: "bg-risk-write",
  exec: "bg-risk-exec",
  network: "bg-risk-network",
  sensitive: "bg-risk-sensitive",
};

export const RISK_TEXT: Record<RiskTier, string> = {
  info: "text-risk-info",
  write: "text-risk-write",
  exec: "text-risk-exec",
  network: "text-risk-network",
  sensitive: "text-risk-sensitive",
};
