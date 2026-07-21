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
  exit_ok: boolean | null; // null = no PostToolUse observed yet — unresolved, not "ok"
  risk: RiskTier;
  risk_reasons?: string;
  reasoning_text?: string;
  capture_gap: boolean;
  git_branch?: string;
  git_head?: string;
  git_dirty: boolean | null; // null = git status unavailable (no repo, git missing, timed out)
  files_touched?: string[];
  created_at: number;
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
