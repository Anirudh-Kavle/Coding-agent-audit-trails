import type { FlightEvent, RiskTier } from "../types";

// HH:MM:SS in local time — mono, used in row + drawer.
export function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString("en-GB", { hour12: false });
}

// Day bucket label for the session sidebar grouping.
export function dayLabel(ts: number): string {
  const d = new Date(ts);
  const today = new Date();
  const yesterday = new Date(today.getTime() - 86_400_000);
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (same(d, today)) return "today";
  if (same(d, yesterday)) return "yesterday";
  return d.toLocaleDateString("en-GB", { month: "short", day: "numeric" });
}

// One-line terminal-style summary of what the action did (mono in the row).
export function eventSummary(e: FlightEvent): string {
  const a = e.arguments_json || {};
  switch (e.tool) {
    case "Bash":
      return String(a.command ?? "");
    case "Read":
    case "Write":
      return String(a.file_path ?? "");
    case "Edit":
    case "NotebookEdit":
      return String(a.file_path ?? "");
    case "WebFetch":
      return `${a.method ?? "GET"} ${a.url ?? ""}`.trim();
    case "Glob":
    case "Grep":
      return String(a.pattern ?? a.query ?? "");
    default:
      // MCP tools + anything unknown: show the first stringy arg, else the tool name.
      for (const v of Object.values(a)) {
        if (typeof v === "string") return v;
      }
      return e.tool;
  }
}

// First line of reasoning for the inline "↳ why:" hint (muted italic in the row).
export function reasoningFirstLine(e: FlightEvent): string | null {
  if (e.capture_gap || !e.reasoning_text) return null;
  const line = e.reasoning_text.trim().split("\n")[0];
  return line.length > 120 ? line.slice(0, 117) + "…" : line;
}

// Short git SHA (mono), defensive against already-short or missing values.
export function shortSha(head?: string): string {
  return head ? head.slice(0, 7) : "—";
}

// Clean-markdown export of one event — feeds the S1 incident-report story.
export function eventToMarkdown(e: FlightEvent): string {
  const lines = [
    `### ${e.tool} · ${e.risk} · ${formatTime(e.ts)}`,
    "",
    "**What**",
    "```",
    eventSummary(e),
    "```",
    "",
    "**Why**",
    e.capture_gap
      ? "_reasoning unavailable (transcript compacted before capture)_"
      : e.reasoning_text || "_none captured_",
    "",
    "**Context**",
    `- cwd branch: \`${e.git_branch ?? "—"}\` @ \`${shortSha(e.git_head)}\`${e.git_dirty ? " (dirty)" : ""}`,
    `- session: \`${e.session_id}\``,
  ];
  return lines.join("\n");
}

// Sort newest-first (timeline is newest-at-top in live mode).
export function byNewest(a: FlightEvent, b: FlightEvent): number {
  return b.ts - a.ts;
}

export const isRiskTier = (v: string): v is RiskTier =>
  ["info", "write", "exec", "network", "sensitive"].includes(v);
