import { useEffect, useState } from "react";
import type { FlightEvent } from "../types";
import { formatTime, shortSha, eventToMarkdown } from "../lib/format";
import { RiskBadge } from "./RiskBadge";

type Tab = "what" | "why" | "context" | "result";
const TABS: { id: Tab; label: string }[] = [
  { id: "what", label: "WHAT" },
  { id: "why", label: "WHY" },
  { id: "context", label: "CONTEXT" },
  { id: "result", label: "RESULT" },
];

interface Props {
  event: FlightEvent | null;
  onClose: () => void;
}

// The money view: slides up on row click, four tabs. Reasoning is the crown jewel.
export function DetailDrawer({ event, onClose }: Props) {
  const [tab, setTab] = useState<Tab>("what");
  const [copied, setCopied] = useState(false);

  // Reset to WHAT (and clear copy state) whenever a different event opens.
  useEffect(() => {
    setTab("what");
    setCopied(false);
  }, [event?.id]);

  if (!event) return null;

  const copy = async () => {
    await navigator.clipboard.writeText(eventToMarkdown(event));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <>
      {/* Backdrop over the timeline; click closes. */}
      <div className="absolute inset-0 z-20 bg-black/40" onClick={onClose} aria-hidden />

      <section
        role="dialog"
        aria-label="Event detail"
        className="fr-slide-in-right absolute inset-y-0 right-0 z-30 flex w-[min(42rem,92vw)] flex-col border-l border-border bg-surface shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-border px-5 py-3">
          <RiskBadge risk={event.risk} />
          <span className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-xs uppercase tracking-wide text-ink-muted">
            {event.tool}
          </span>
          <time className="font-mono text-xs text-ink-faint">{formatTime(event.ts)}</time>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={copy}
              className="cursor-pointer rounded border border-border px-2 py-1 text-xs text-ink-muted transition-colors hover:border-border hover:text-ink"
            >
              {copied ? "copied ✓" : "copy markdown"}
            </button>
            <button
              onClick={onClose}
              aria-label="Close detail"
              className="cursor-pointer rounded p-1 text-ink-faint transition-colors hover:text-ink"
            >
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden>
                <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-border px-3">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={[
                "cursor-pointer border-b-2 px-3 py-2 text-xs font-medium tracking-wide transition-colors",
                tab === t.id
                  ? "border-b-ink text-ink"
                  : "border-b-transparent text-ink-faint hover:text-ink-muted",
              ].join(" ")}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="min-h-0 min-w-0 flex-1 overflow-y-auto p-5">
          {tab === "what" && <WhatTab event={event} />}
          {tab === "why" && <WhyTab event={event} />}
          {tab === "context" && <ContextTab event={event} />}
          {tab === "result" && <ResultTab event={event} />}
        </div>
      </section>
    </>
  );
}

function WhatTab({ event }: { event: FlightEvent }) {
  return (
    <div className="space-y-4">
      <Json label="arguments" value={event.arguments_json} />
      {event.files_touched && event.files_touched.length > 0 && (
        <div>
          <Label>files touched</Label>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {event.files_touched.map((f) => (
              <code key={f} className="rounded bg-surface-2 px-2 py-0.5 font-mono text-xs text-ink">
                {f}
              </code>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function WhyTab({ event }: { event: FlightEvent }) {
  if (event.capture_gap || !event.reasoning_text) {
    return (
      <div className="rounded-md border border-risk-exec/40 bg-risk-exec/5 p-4">
        <p className="text-sm font-medium text-risk-exec">reasoning unavailable</p>
        <p className="mt-1 text-sm text-ink-muted">
          The transcript was compacted or deleted before this action's reasoning could be
          captured. We never fabricate a "why" — this gap is recorded honestly.
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <span className="inline-flex items-center gap-1.5 rounded-full border border-risk-write/40 bg-risk-write/10 px-2.5 py-0.5 text-xs text-risk-write">
        <span className="h-1.5 w-1.5 rounded-full bg-risk-write" aria-hidden />
        captured live before compaction
      </span>
      <p className="max-w-[70ch] text-[15px] leading-[1.6] text-ink">{event.reasoning_text}</p>
    </div>
  );
}

function ContextTab({ event }: { event: FlightEvent }) {
  return (
    <dl className="grid grid-cols-[8rem_minmax(0,1fr)] gap-x-4 gap-y-2.5 text-sm">
      <Row k="git branch" v={event.git_branch ?? "—"} mono />
      <Row k="HEAD" v={`${shortSha(event.git_head)}${event.git_dirty ? "  (dirty)" : ""}`} mono />
      <Row k="session" v={event.session_id} mono />
      <Row k="phase" v={event.phase} mono />
      {event.risk_reasons && <Row k="risk reasons" v={event.risk_reasons} />}
    </dl>
  );
}

function ResultTab({ event }: { event: FlightEvent }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm">
        <Label>exit</Label>
        <span className={event.exit_ok ? "text-risk-write" : "text-risk-sensitive"}>
          {event.exit_ok ? "ok" : "failed"}
        </span>
      </div>
      <Json label="result" value={event.result_json ?? { note: "no result recorded" }} />
    </div>
  );
}

function Json({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <Label>{label}</Label>
      <pre className="mt-1.5 overflow-x-auto rounded-md border border-border-soft bg-bg p-3 font-mono text-xs leading-relaxed text-ink">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono text-[10px] uppercase tracking-wider text-ink-faint">{children}</span>
  );
}

function Row({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <>
      <dt className="font-mono text-[10px] uppercase tracking-wider text-ink-faint">{k}</dt>
      <dd className={[mono ? "font-mono" : "", "text-ink break-all"].join(" ")}>{v}</dd>
    </>
  );
}
