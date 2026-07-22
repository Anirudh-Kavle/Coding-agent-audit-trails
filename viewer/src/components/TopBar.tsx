import { forwardRef, useEffect, useState } from "react";
import type { Session } from "../types";
import type { Provider } from "../lib/agents";
import type { BudgetSetting } from "../lib/api";
import { RecordingToggle } from "./RecordingToggle";
import { SearchBar } from "./SearchBar";

interface Props {
  search: string;
  onSearch: (v: string) => void;
  onClearSearch: () => void;
  sessions: Session[];
  agentFilter: Provider | null;
  sessionBudget?: { id: string; used: number; limit: number; timeLimit?: number };
  dailyTokens: number;
  budgets: BudgetSetting[];
  onBudgetSaved: (scope: string, tokenLimit: number | null, timeLimit: number | null) => Promise<void>;
}

export const TopBar = forwardRef<HTMLInputElement, Props>(
  ({ search, onSearch, onClearSearch, sessions, agentFilter, sessionBudget, dailyTokens, budgets, onBudgetSaved }, ref) => {
    const [editing, setEditing] = useState(false);
    const [tokens, setTokens] = useState(sessionBudget?.limit ? String(sessionBudget.limit) : "");
    const [seconds, setSeconds] = useState(sessionBudget?.timeLimit?.toString() ?? "");
    const [saveError, setSaveError] = useState("");
    const TOKEN_PRESETS = [10_000, 20_000, 50_000, 100_000];
    const TIME_PRESETS: [number, string][] = [
      [900, "15m"],
      [1800, "30m"],
      [3600, "1h"],
      [14400, "4h"],
      [86400, "24h"],
    ];
    const selectedBudget = budgets.find((b) => b.scope === "openai-api");
    useEffect(() => { setTokens(selectedBudget?.token_limit?.toString() ?? ""); }, [selectedBudget?.token_limit]);
    useEffect(() => { setSeconds(selectedBudget?.time_limit_s?.toString() ?? ""); }, [selectedBudget?.time_limit_s]);
    const remaining = sessionBudget ? Math.max(0, sessionBudget.limit - sessionBudget.used) : null;
    const percent = sessionBudget ? Math.max(0, Math.min(100, remaining! / sessionBudget.limit * 100)) : 0;
    return (
      <header className="relative z-50 flex items-center gap-4 border-b border-border bg-surface/60 px-5 py-3 text-sm backdrop-blur">
        <div className="flex shrink-0 items-center gap-2">
          <img src="/favicon.png" alt="" className="h-5 w-5 rounded-sm" />
          <span className="font-mono font-semibold tracking-tight text-ink">
            Zetesis
          </span>
        </div>

        <div className="min-w-0 flex-1">
          <SearchBar ref={ref} value={search} onChange={onSearch} onClear={onClearSearch} sessions={sessions} agentFilter={agentFilter} />
        </div>

        <div className="relative flex shrink-0 items-center gap-3">
          <button
            type="button"
            onClick={() => setEditing((v) => !v)}
            title={sessionBudget ? `${remaining!.toLocaleString()} tokens left in this session` : "No token limit selected"}
            className="flex cursor-pointer items-center gap-2 rounded-md border border-border px-3 py-1.5 font-mono text-sm text-ink-muted transition-colors hover:border-ink-faint hover:text-ink"
          >
            <span className="relative h-4 w-4 shrink-0 rounded-full" style={{ background: sessionBudget ? `conic-gradient(#60a5fa ${percent}%, #273244 ${percent}% 100%)` : "#273244" }}>
              <span className="absolute inset-[3px] rounded-full bg-surface" />
            </span>
            <span className="whitespace-nowrap">
              {sessionBudget ? `${remaining!.toLocaleString()} left` : "Set budget"}
            </span>
            <span className="whitespace-nowrap text-ink-faint">· {dailyTokens.toLocaleString()} today</span>
          </button>
          {editing && <form style={{ backgroundColor: "#10151d", opacity: 1 }} className="absolute right-0 top-10 z-[9999] w-80 rounded-lg border border-border p-4 shadow-2xl ring-1 ring-black/80" onSubmit={async (e) => { e.preventDefault(); setSaveError(""); try { await onBudgetSaved("openai-api", tokens ? Number(tokens) : null, seconds ? Number(seconds) : null); setEditing(false); } catch (err) { setSaveError(err instanceof Error ? err.message : "Save failed"); } }}>
            <div className="mb-1 text-xs font-semibold text-ink">API token budget</div>
            <div className="mb-2 rounded border border-border-soft bg-black/20 px-2 py-1.5 text-[11px] text-ink-faint">
              {selectedBudget?.token_limit == null
                ? "No token cap selected"
                : `${selectedBudget.token_used.toLocaleString()} used · ${Math.max(0, selectedBudget.token_limit - selectedBudget.token_used).toLocaleString()} remaining of ${selectedBudget.token_limit.toLocaleString()}`}
            </div>
            <p className="mb-2 text-[11px] text-ink-faint">
              This limit applies to the Zetesis API agent and is enforced before each request.
            </p>

            <label className="mb-1 block text-xs">Token limit</label>
            <input
              className="mb-1.5 w-full rounded bg-black/20 px-2 py-1 text-xs text-ink"
              type="text"
              inputMode="numeric"
              value={tokens}
              onChange={(e) => setTokens(e.target.value.replace(/\D/g, ""))}
            />
            <div className="mb-3 flex flex-wrap gap-1">
              {TOKEN_PRESETS.map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setTokens(String(v))}
                  className={`cursor-pointer rounded border px-2 py-0.5 text-[11px] transition-colors ${
                    tokens === String(v)
                      ? "border-transparent bg-risk-write/20 text-risk-write"
                      : "border-border-soft bg-surface-2 text-ink-muted hover:border-border hover:text-ink"
                  }`}
                >
                  {v.toLocaleString()}
                </button>
              ))}
            </div>

            <label className="mb-1 block text-xs">Time limit (seconds)</label>
            <input
              className="mb-1.5 w-full rounded bg-black/20 px-2 py-1 text-xs text-ink"
              type="text"
              inputMode="numeric"
              value={seconds}
              onChange={(e) => setSeconds(e.target.value.replace(/\D/g, ""))}
            />
            <div className="mb-3 flex flex-wrap gap-1">
              {TIME_PRESETS.map(([v, label]) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setSeconds(String(v))}
                  className={`cursor-pointer rounded border px-2 py-0.5 text-[11px] transition-colors ${
                    seconds === String(v)
                      ? "border-transparent bg-risk-write/20 text-risk-write"
                      : "border-border-soft bg-surface-2 text-ink-muted hover:border-border hover:text-ink"
                  }`}
                >
                  {v}s ({label})
                </button>
              ))}
            </div>

            <button className="cursor-pointer rounded bg-blue-500 px-3 py-1 text-xs text-white hover:bg-blue-400" type="submit">Save limits</button>
            {saveError && <div className="mt-2 text-xs text-red-300">{saveError}</div>}
          </form>}
          <RecordingToggle />
        </div>
      </header>
    );
  }
);
TopBar.displayName = "TopBar";
