import { describe, expect, it } from "vitest";
import { normalizeEvent, normalizeSession } from "./api";

// Raw wire shapes as the FastAPI backend actually sends them.
const rawEvent = {
  id: 42,
  session_id: "sess_x",
  ts: 1_752_700_000_000,
  phase: "post",
  tool: "Bash",
  arguments_json: '{"command":"npm test"}',
  result_json: '{"stdout":"ok","exit_code":0}',
  exit_ok: 1 as const,
  reasoning_text: "Running the suite.",
  risk: "exec",
  risk_reasons: ["Shell command execution"],
  capture_gap: 0 as const,
  git_branch: "mvp",
  git_head: "210341b",
  git_dirty: 1 as const,
  files_touched: '["a.ts","b.ts"]',
};

describe("normalizeEvent", () => {
  it("coerces a full raw event", () => {
    const e = normalizeEvent(rawEvent);
    expect(e.arguments_json).toEqual({ command: "npm test" });
    expect(e.result_json).toEqual({ stdout: "ok", exit_code: 0 });
    expect(e.exit_ok).toBe(true);
    expect(e.capture_gap).toBe(false);
    expect(e.git_dirty).toBe(true);
    expect(e.risk).toBe("exec");
    expect(e.risk_reasons).toBe("Shell command execution");
    expect(e.files_touched).toEqual(["a.ts", "b.ts"]);
    expect(e.created_at).toBe(rawEvent.ts);
  });

  it("wraps truncated (invalid) JSON instead of throwing", () => {
    const truncated = '{"command":"' + "x".repeat(50) + "...[truncated]";
    const e = normalizeEvent({ ...rawEvent, arguments_json: truncated });
    expect(e.arguments_json).toEqual({ raw: truncated });
  });

  it("handles a pending pre event (null result, null exit_ok)", () => {
    const e = normalizeEvent({
      ...rawEvent,
      phase: "pre",
      result_json: null,
      exit_ok: null,
    });
    expect(e.result_json).toBeUndefined();
    expect(e.exit_ok).toBe(true); // pending must not render as failed
  });

  it("maps failed post events to exit_ok false", () => {
    expect(normalizeEvent({ ...rawEvent, exit_ok: 0 }).exit_ok).toBe(false);
  });

  it("tolerates garbage and null files_touched", () => {
    expect(normalizeEvent({ ...rawEvent, files_touched: "not json" }).files_touched).toEqual([]);
    expect(normalizeEvent({ ...rawEvent, files_touched: null }).files_touched).toEqual([]);
  });

  it("joins risk_reasons lists, passes strings, drops empties", () => {
    expect(normalizeEvent({ ...rawEvent, risk_reasons: ["a", "b"] }).risk_reasons).toBe("a; b");
    expect(normalizeEvent({ ...rawEvent, risk_reasons: "test" }).risk_reasons).toBe("test");
    expect(normalizeEvent({ ...rawEvent, risk_reasons: [] }).risk_reasons).toBeUndefined();
    expect(normalizeEvent({ ...rawEvent, risk_reasons: null }).risk_reasons).toBeUndefined();
  });

  it("falls back to info for unknown risk tiers", () => {
    expect(normalizeEvent({ ...rawEvent, risk: "mystery" }).risk).toBe("info");
  });

  it("wraps JSON non-objects in { raw }", () => {
    expect(normalizeEvent({ ...rawEvent, result_json: '"just a string"' }).result_json).toEqual({
      raw: '"just a string"',
    });
  });
});

const rawSession = {
  id: "sess_x",
  started_at: 1_752_700_000_000,
  ended_at: null,
  cwd: "/Users/dev/project",
  git_repo: "project",
  source: "startup",
  title: null,
};

describe("normalizeSession", () => {
  it("derives live from ended_at", () => {
    expect(normalizeSession(rawSession).live).toBe(true);
    expect(normalizeSession({ ...rawSession, ended_at: 1 }).live).toBe(false);
  });

  it("maps Claude Code source values onto the viewer union", () => {
    expect(normalizeSession({ ...rawSession, source: "startup" }).source).toBe("interactive");
    expect(normalizeSession({ ...rawSession, source: "resume" }).source).toBe("resumed");
    expect(normalizeSession({ ...rawSession, source: "clear" }).source).toBe("interactive");
    expect(normalizeSession({ ...rawSession, source: "compact" }).source).toBe("interactive");
    expect(normalizeSession({ ...rawSession, source: null }).source).toBe("interactive");
    expect(normalizeSession({ ...rawSession, source: "garbage" }).source).toBe("interactive");
  });

  it("converts null optionals to undefined", () => {
    const s = normalizeSession({ ...rawSession, git_repo: null });
    expect(s.git_repo).toBeUndefined();
    expect(s.ended_at).toBeUndefined();
  });

  it("maps title onto label, the Claude Code sidebar name", () => {
    expect(normalizeSession({ ...rawSession, title: "Brainstorm art contest project ideas" }).label).toBe(
      "Brainstorm art contest project ideas",
    );
    expect(normalizeSession({ ...rawSession, title: null }).label).toBeUndefined();
  });
});
