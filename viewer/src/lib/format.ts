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

// Minimal JSON syntax highlighter — no dependency, since the only "language"
// the drawer ever needs to color is JSON. One token per string/number/
// boolean/null; everything else (braces, commas, whitespace) stays plain.
export type JsonTokenType = "key" | "string" | "number" | "boolean" | "null" | "punctuation";

export interface JsonToken {
  text: string;
  type: JsonTokenType;
}

const JSON_TOKEN_RE = /"(?:\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"|\btrue\b|\bfalse\b|\bnull\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g;

export function tokenizeJson(text: string): JsonToken[] {
  const tokens: JsonToken[] = [];
  let lastIndex = 0;

  for (const match of text.matchAll(JSON_TOKEN_RE)) {
    const raw = match[0];
    const index = match.index ?? 0;
    if (index > lastIndex) {
      tokens.push({ text: text.slice(lastIndex, index), type: "punctuation" });
    }

    let type: JsonTokenType;
    if (raw.startsWith('"')) {
      // A quoted string immediately followed by a colon is an object key —
      // peek forward rather than consuming the colon into the token, so the
      // colon itself stays plain punctuation.
      type = /^\s*:/.test(text.slice(index + raw.length)) ? "key" : "string";
    } else if (raw === "true" || raw === "false") {
      type = "boolean";
    } else if (raw === "null") {
      type = "null";
    } else {
      type = "number";
    }
    tokens.push({ text: raw, type });
    lastIndex = index + raw.length;
  }

  if (lastIndex < text.length) {
    tokens.push({ text: text.slice(lastIndex), type: "punctuation" });
  }
  return tokens;
}

export function highlightJson(value: unknown): JsonToken[] {
  return tokenizeJson(JSON.stringify(value, null, 2));
}

// Short git SHA (mono), defensive against already-short or missing values.
export function shortSha(head?: string): string {
  return head ? head.slice(0, 7) : "—";
}

// Suffix for the HEAD row — null means git status couldn't be read, not "clean".
export function gitDirtySuffix(dirty: boolean | null): string {
  if (dirty === null) return " (dirty: unknown)";
  return dirty ? " (dirty)" : "";
}

// Per-section markdown — each drawer tab can be copied on its own.
export function whatToMarkdown(e: FlightEvent): string {
  const lines = [
    "**What**",
    "```",
    eventSummary(e),
    "```",
  ];
  if (e.files_touched && e.files_touched.length > 0) {
    lines.push("", "files touched:", ...e.files_touched.map((f) => `- \`${f}\``));
  }
  return lines.join("\n");
}

export function whyToMarkdown(e: FlightEvent): string {
  return [
    "**Why**",
    e.capture_gap
      ? "_reasoning unavailable (transcript compacted before capture)_"
      : e.reasoning_text || "_none captured_",
  ].join("\n");
}

export function contextToMarkdown(e: FlightEvent): string {
  const lines = [
    "**Context**",
    `- cwd branch: \`${e.git_branch ?? "—"}\` @ \`${shortSha(e.git_head)}\`${e.git_dirty ? " (dirty)" : ""}`,
    `- session: \`${e.session_id}\``,
    `- phase: \`${e.phase}\``,
  ];
  if (e.risk_reasons) lines.push(`- risk reasons: ${e.risk_reasons}`);
  return lines.join("\n");
}

export function resultToMarkdown(e: FlightEvent): string {
  return [
    "**Result**",
    `- exit: ${e.exit_ok ? "ok" : "failed"}`,
    "```",
    JSON.stringify(e.result_json ?? { note: "no result recorded" }, null, 2),
    "```",
  ].join("\n");
}

// Clean-markdown export of one event — feeds the S1 incident-report story.
export function eventToMarkdown(e: FlightEvent): string {
  const lines = [
    `### ${e.tool} · ${e.risk} · ${formatTime(e.ts)}`,
    "",
    whatToMarkdown(e),
    "",
    whyToMarkdown(e),
    "",
    contextToMarkdown(e),
    "",
    resultToMarkdown(e),
  ];
  return lines.join("\n");
}

// Sort newest-first (timeline is newest-at-top in live mode).
export function byNewest(a: FlightEvent, b: FlightEvent): number {
  return b.ts - a.ts;
}

export const isRiskTier = (v: string): v is RiskTier =>
  ["info", "write", "exec", "network", "sensitive"].includes(v);
