import { forwardRef, useEffect, useState } from "react";
import { RecIndicator } from "./RecIndicator";
import { RecordingToggle } from "./RecordingToggle";
import { SearchBar } from "./SearchBar";

interface Props {
  live: boolean;
  search: string;
  onSearch: (v: string) => void;
  onClearSearch: () => void;
  sessionBudget?: { id: string; used: number; limit: number; timeLimit?: number };
  dailyTokens: number;
  onBudgetSaved: (tokenLimit: number | null, timeLimit: number | null) => Promise<void>;
}

export const TopBar = forwardRef<HTMLInputElement, Props>(
  ({ live, search, onSearch, onClearSearch, sessionBudget, dailyTokens, onBudgetSaved }, ref) => {
    const [editing, setEditing] = useState(false);
    const [tokens, setTokens] = useState(sessionBudget?.limit ? String(sessionBudget.limit) : "");
    const [seconds, setSeconds] = useState(sessionBudget?.timeLimit?.toString() ?? "");
    const [saveError, setSaveError] = useState("");
    useEffect(() => { setTokens(sessionBudget?.limit ? String(sessionBudget.limit) : ""); }, [sessionBudget?.limit]);
    useEffect(() => { setSeconds(sessionBudget?.timeLimit?.toString() ?? ""); }, [sessionBudget?.timeLimit]);
    // limit 0 = no limit set yet — the editor still opens so one can be created.
    const hasLimit = !!sessionBudget && sessionBudget.limit > 0;
    const remaining = hasLimit ? Math.max(0, sessionBudget!.limit - sessionBudget!.used) : null;
    const percent = hasLimit ? Math.max(0, Math.min(100, remaining! / sessionBudget!.limit * 100)) : 0;
    return (
      <header className="relative z-50 flex items-center gap-6 border-b border-border bg-surface/60 px-5 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <RecIndicator live={live} />
          <span className="font-mono text-sm font-semibold tracking-tight text-ink">
            Flight&nbsp;Recorder
          </span>
        </div>
        <div className="relative flex items-center gap-2 text-xs text-muted" title={hasLimit ? `${remaining!.toLocaleString()} tokens left of this session's ${sessionBudget!.limit.toLocaleString()} budget — click to change` : "No token budget set for this session — click to set token/time limits for the API agent"}>
          <button type="button" className="flex items-center gap-2 rounded px-1 py-1 hover:bg-white/10" onClick={() => setEditing((v) => !v)}>
          <span className="relative h-7 w-7 rounded-full" style={{ background: hasLimit ? `conic-gradient(#60a5fa ${percent}%, #273244 ${percent}% 100%)` : "#273244" }}>
            <span className="absolute inset-1 rounded-full bg-surface" />
          </span>
          <span className="whitespace-nowrap">
            {hasLimit ? `${remaining!.toLocaleString()} tokens left` : "Set session budget"}
            <span className="ml-2 text-muted/70" title="API tokens used today across all sessions">Today: {dailyTokens.toLocaleString()}</span>
          </span>
          </button>
          {editing && sessionBudget && <form style={{ backgroundColor: "#10151d", opacity: 1 }} className="absolute left-0 top-10 z-[9999] w-72 rounded-lg border border-border p-4 shadow-2xl ring-1 ring-black/80" onSubmit={async (e) => { e.preventDefault(); setSaveError(""); try { await onBudgetSaved(tokens ? Number(tokens) : null, seconds ? Number(seconds) : null); setEditing(false); } catch (err) { setSaveError(err instanceof Error ? err.message : "Save failed"); } }}>
            <div className="mb-2 text-xs font-semibold text-ink" title="Limits apply to the API agent (fr api-ui) for this session — when hit, no further API calls are made">
              Session limits · {sessionBudget!.id.slice(0, 8)}
            </div>
            <label className="mb-2 block text-xs">Token limit<input className="mt-1 w-full rounded bg-black/20 px-2 py-1 text-xs text-ink" type="number" min="1" value={tokens} onChange={(e) => setTokens(e.target.value)} /></label>
            <label className="mb-2 block text-xs">Time limit (seconds)<input className="mt-1 w-full rounded bg-black/20 px-2 py-1 text-xs text-ink" type="number" min="1" value={seconds} onChange={(e) => setSeconds(e.target.value)} /></label>
            <button className="rounded bg-blue-500 px-3 py-1 text-xs text-white" type="submit">Save limits</button>
            {saveError && <div className="mt-2 text-xs text-red-300">{saveError}</div>}
          </form>}
        </div>
        <div className="flex-1">
          <SearchBar ref={ref} value={search} onChange={onSearch} onClear={onClearSearch} />
        </div>
        <RecordingToggle />
      </header>
    );
  }
);
TopBar.displayName = "TopBar";
