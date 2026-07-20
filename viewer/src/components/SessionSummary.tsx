import { useEffect, useState } from "react";
import type { SessionSummary as Summary } from "../types";
import { dataSource } from "../lib/dataSource";

interface Props {
  sessionId: string;
  onOpenEvent: (id: number) => void;
}

const CITATION_RE = /\[event\s+(\d+)\]/gi;

// Render summary prose with [event N] citations as clickable links — the
// verification path that keeps the local model honest.
function CitedText({ text, onOpenEvent }: { text: string; onOpenEvent: (id: number) => void }) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(CITATION_RE)) {
    const idx = match.index ?? 0;
    if (idx > last) parts.push(text.slice(last, idx));
    const id = Number(match[1]);
    parts.push(
      <button
        key={`${idx}-${id}`}
        onClick={() => onOpenEvent(id)}
        className="cursor-pointer rounded bg-surface-2 px-1 font-mono text-ink underline decoration-dotted hover:decoration-solid"
        title={`Open event ${id}`}
      >
        [{id}]
      </button>
    );
    last = idx + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts}</>;
}

type State =
  | { kind: "loading" }
  | { kind: "hidden" } // no model on this install
  | { kind: "none" } // model available, nothing generated yet
  | { kind: "generating" }
  | { kind: "ready"; summary: Summary }
  | { kind: "error"; message: string };

export function SessionSummaryPanel({ sessionId, onOpenEvent }: Props) {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let stale = false;
    setState({ kind: "loading" });
    dataSource
      .getSummary(sessionId)
      .then((r) => {
        if (stale) return;
        if (r.summary) setState({ kind: "ready", summary: r.summary });
        else if (r.available) setState({ kind: "none" });
        else setState({ kind: "hidden" });
      })
      .catch(() => !stale && setState({ kind: "hidden" }));
    return () => {
      stale = true;
    };
  }, [sessionId]);

  const generate = () => {
    setState({ kind: "generating" });
    dataSource
      .generateSummary(sessionId)
      .then((r) => {
        if (r.summary) setState({ kind: "ready", summary: r.summary });
        else setState({ kind: "error", message: r.error ?? "no summary produced" });
      })
      .catch((e: Error) => setState({ kind: "error", message: e.message }));
  };

  if (state.kind === "hidden" || state.kind === "loading") return null;

  return (
    <div className="border-b border-border bg-surface px-4 py-2 text-sm">
      {state.kind === "ready" ? (
        <div className="flex items-start gap-2">
          <span className="mt-0.5 shrink-0 font-mono text-xs uppercase tracking-wide text-ink-faint">
            summary
          </span>
          <p className="min-w-0 leading-relaxed text-ink-muted">
            <CitedText text={state.summary.text} onOpenEvent={onOpenEvent} />
            {state.summary.model && (
              <span className="ml-2 font-mono text-xs text-ink-faint">
                · {state.summary.model} (local)
              </span>
            )}
            <button
              onClick={generate}
              className="ml-2 cursor-pointer font-mono text-xs text-ink-faint hover:text-ink"
              title="Regenerate with the local model"
            >
              ↻
            </button>
          </p>
        </div>
      ) : state.kind === "generating" ? (
        <span className="font-mono text-xs text-ink-muted">
          <span className="animate-pulse">●</span> summarizing with local model — takes ~30s on
          CPU, nothing leaves this machine…
        </span>
      ) : state.kind === "error" ? (
        <span className="font-mono text-xs text-risk-exec">
          summary failed: {state.message}{" "}
          <button onClick={generate} className="cursor-pointer underline">
            retry
          </button>
        </span>
      ) : (
        <button
          onClick={generate}
          className="cursor-pointer font-mono text-xs text-ink-muted hover:text-ink"
        >
          ✦ Generate session summary (local model, ~30s, free)
        </button>
      )}
    </div>
  );
}
