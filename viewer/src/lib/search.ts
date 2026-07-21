import type { FlightEvent } from "../types";
import { eventSummary } from "./format";

export interface ParsedQuery {
  text: string[]; // free-text terms
  tool?: string;
  risk?: string;
  file?: string;
  session?: string;
  agent?: string;
}

const QUALIFIERS = ["tool", "risk", "file", "session", "agent"] as const;

// Hand-rolled qualifier parser (spec 3.2) — tool: risk: file: session: + free text. No lib.
export function parseQuery(q: string): ParsedQuery {
  const out: ParsedQuery = { text: [] };
  for (const token of q.trim().split(/\s+/).filter(Boolean)) {
    const m = token.match(/^(\w+):(.*)$/);
    if (m && (QUALIFIERS as readonly string[]).includes(m[1])) {
      (out as unknown as Record<string, string>)[m[1]] = m[2].toLowerCase();
    } else {
      out.text.push(token.toLowerCase());
    }
  }
  return out;
}

// Which qualifier the user is mid-typing, for the chip hint UI.
export function activeQualifier(q: string): string | null {
  const last = q.split(/\s+/).pop() ?? "";
  const m = last.match(/^(\w+):$/);
  return m && (QUALIFIERS as readonly string[]).includes(m[1]) ? m[1] : null;
}

// A qualifier value can be a comma-separated OR-list (risk:write,exec) — the
// filter panel writes these when more than one checkbox is checked. `tool:`
// additionally supports `+`-joined aliases within one element (a single tool
// tag can cover several raw names, e.g. Codex's "bash+run_command") and a
// trailing `*` for prefix matches (mcp__*).
function splitList(value: string): string[] {
  return value.split(",").map((v) => v.trim()).filter(Boolean);
}

export function filterEvents(events: FlightEvent[], q: string): FlightEvent[] {
  const p = parseQuery(q);
  return events.filter((e) => {
    if (p.tool) {
      const tokens = splitList(p.tool).flatMap((t) => t.split("+"));
      const lower = e.tool.toLowerCase();
      const match = tokens.some((t) => (t.endsWith("*") ? lower.startsWith(t.slice(0, -1)) : lower === t));
      if (!match) return false;
    }
    if (p.risk && !splitList(p.risk).includes(e.risk)) return false;
    if (p.agent && e.provider.toLowerCase() !== p.agent) return false;
    if (p.session) {
      const lower = e.session_id.toLowerCase();
      if (!splitList(p.session).some((s) => lower.includes(s))) return false;
    }
    if (p.file) {
      const files = (e.files_touched ?? []).join(" ").toLowerCase();
      if (!files.includes(p.file)) return false;
    }
    if (p.text.length) {
      const hay = (
        eventSummary(e) +
        " " +
        (e.reasoning_text ?? "") +
        " " +
        e.tool
      ).toLowerCase();
      if (!p.text.every((t) => hay.includes(t))) return false;
    }
    return true;
  });
}

export const SEARCH_QUALIFIERS = QUALIFIERS;
