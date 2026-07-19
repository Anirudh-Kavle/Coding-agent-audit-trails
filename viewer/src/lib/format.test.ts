import { describe, it, expect } from "vitest";
import type { FlightEvent } from "../types";
import { eventSummary, reasoningFirstLine, shortSha, dayLabel } from "./format";
import { parseQuery, filterEvents, activeQualifier } from "./search";

const base: FlightEvent = {
  id: 1,
  session_id: "s1",
  ts: Date.now(),
  phase: "post",
  tool: "Bash",
  arguments_json: { command: "npm test" },
  exit_ok: true,
  risk: "exec",
  reasoning_text: "Running the suite to confirm the change is green.",
  capture_gap: false,
  git_dirty: false,
  files_touched: [],
  created_at: Date.now(),
};

describe("eventSummary", () => {
  it("shows the command for Bash", () => {
    expect(eventSummary(base)).toBe("npm test");
  });
  it("shows file_path for Edit/Read/Write", () => {
    expect(eventSummary({ ...base, tool: "Edit", arguments_json: { file_path: "a.ts" } })).toBe("a.ts");
  });
  it("shows METHOD url for WebFetch", () => {
    expect(
      eventSummary({ ...base, tool: "WebFetch", arguments_json: { url: "http://x", method: "POST" } })
    ).toBe("POST http://x");
  });
  it("falls back to first string arg for unknown/MCP tools", () => {
    expect(eventSummary({ ...base, tool: "mcp__foo", arguments_json: { q: "hi" } })).toBe("hi");
  });
});

describe("reasoningFirstLine", () => {
  it("returns null on capture_gap (never fabricates a why)", () => {
    expect(reasoningFirstLine({ ...base, capture_gap: true, reasoning_text: undefined })).toBeNull();
  });
  it("returns the first line otherwise", () => {
    expect(reasoningFirstLine({ ...base, reasoning_text: "line one\nline two" })).toBe("line one");
  });
});

describe("shortSha", () => {
  it("truncates to 7 chars", () => {
    expect(shortSha("a1b2c3d4e5")).toBe("a1b2c3d");
  });
  it("handles missing head", () => {
    expect(shortSha(undefined)).toBe("—");
  });
});

describe("dayLabel", () => {
  it("labels today", () => {
    expect(dayLabel(Date.now())).toBe("today");
  });
  it("labels yesterday", () => {
    expect(dayLabel(Date.now() - 86_400_000)).toBe("yesterday");
  });
});

describe("parseQuery", () => {
  it("splits qualifiers from free text", () => {
    const p = parseQuery("useradd tool:bash risk:sensitive");
    expect(p.tool).toBe("bash");
    expect(p.risk).toBe("sensitive");
    expect(p.text).toEqual(["useradd"]);
  });
  it("treats unknown prefixes as free text", () => {
    expect(parseQuery("foo:bar").text).toEqual(["foo:bar"]);
  });
});

describe("activeQualifier", () => {
  it("detects a qualifier being typed", () => {
    expect(activeQualifier("risk:")).toBe("risk");
  });
  it("returns null once a value is present", () => {
    expect(activeQualifier("risk:sensitive")).toBeNull();
  });
});

describe("filterEvents", () => {
  const events: FlightEvent[] = [
    base,
    { ...base, id: 2, tool: "Bash", risk: "sensitive", arguments_json: { command: "useradd svc" } },
    { ...base, id: 3, tool: "Edit", risk: "write", arguments_json: { file_path: "deploy.yaml" }, files_touched: ["deploy.yaml"] },
  ];
  it("filters by risk qualifier", () => {
    expect(filterEvents(events, "risk:sensitive").map((e) => e.id)).toEqual([2]);
  });
  it("filters by tool qualifier", () => {
    expect(filterEvents(events, "tool:edit").map((e) => e.id)).toEqual([3]);
  });
  it("filters by file qualifier against files_touched", () => {
    expect(filterEvents(events, "file:deploy").map((e) => e.id)).toEqual([3]);
  });
  it("free text matches command + reasoning", () => {
    expect(filterEvents(events, "useradd").map((e) => e.id)).toEqual([2]);
  });
});
