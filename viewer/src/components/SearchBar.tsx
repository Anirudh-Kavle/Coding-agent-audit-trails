import { forwardRef, useEffect, useRef, useState } from "react";
import type { Session } from "../types";
import type { Provider } from "../lib/agents";
import { parseQuery } from "../lib/search";
import { FilterPanel } from "./FilterPanel";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onClear: () => void;
  sessions: Session[];
  agentFilter: Provider | null;
}

const QUALIFIER_KEYS = ["tool", "risk", "file", "session", "agent"] as const;

// Plain-text search + a filter icon that slides out a docked panel (not a
// modal) with one collapsible section per facet. The panel writes straight
// into this same text field via qualifier syntax (tool:bash risk:sensitive),
// so typing directly still works — the panel is just a friendlier way to
// build the same string. Esc-to-clear-search is handled globally; Esc here
// only closes the panel (see the capture-phase listener below).
export const SearchBar = forwardRef<HTMLInputElement, Props>(
  ({ value, onChange, onClear, sessions, agentFilter }, ref) => {
    const [panelOpen, setPanelOpen] = useState(false);
    const wrapperRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
      if (!panelOpen) return;
      const onMouseDown = (e: MouseEvent) => {
        if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) setPanelOpen(false);
      };
      const onKeyDown = (e: KeyboardEvent) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          setPanelOpen(false);
        }
      };
      document.addEventListener("mousedown", onMouseDown);
      // Capture phase: close the panel before the app-wide Esc handler (which
      // otherwise clears the whole search) ever sees the event.
      document.addEventListener("keydown", onKeyDown, true);
      return () => {
        document.removeEventListener("mousedown", onMouseDown);
        document.removeEventListener("keydown", onKeyDown, true);
      };
    }, [panelOpen]);

    const parsed = parseQuery(value);
    const activeCount = QUALIFIER_KEYS.filter((k) => Boolean(parsed[k])).length;
    const filterActive = panelOpen || activeCount > 0;

    return (
      <div ref={wrapperRef} className="relative flex w-full max-w-3xl items-center gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5">
          <SearchIcon />
          <input
            ref={ref}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="search actions, reasoning, files…"
            className="w-full bg-transparent font-mono text-sm text-ink placeholder:text-ink-faint focus:outline-none"
            aria-label="Search events"
          />
          {value && (
            <button
              onClick={onClear}
              className="cursor-pointer text-ink-faint transition-colors hover:text-ink"
              aria-label="Clear search"
            >
              <CloseIcon />
            </button>
          )}
        </div>

        <button
          type="button"
          onClick={() => setPanelOpen((v) => !v)}
          aria-label="Filters"
          aria-expanded={panelOpen}
          className={`flex shrink-0 cursor-pointer items-center gap-1.5 rounded-md border px-3 py-1.5 font-mono text-sm transition-colors ${
            filterActive
              ? "border-risk-write/50 bg-risk-write/10 text-risk-write"
              : "border-border text-ink-muted hover:border-ink-faint hover:text-ink"
          }`}
        >
          <FilterIcon />
          Filters{activeCount > 0 ? ` · ${activeCount}` : ""}
          <span className={`text-[10px] transition-transform ${panelOpen ? "" : "rotate-180"}`} aria-hidden>
            ▲
          </span>
        </button>

        {panelOpen && (
          <FilterPanel value={value} onChange={onChange} sessions={sessions} agentFilter={agentFilter} />
        )}
      </div>
    );
  }
);
SearchBar.displayName = "SearchBar";

function SearchIcon() {
  return (
    <svg className="h-4 w-4 shrink-0 text-ink-faint" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
      <path d="m20 20-3-3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function FilterIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M4 6h16M7 12h10M10 18h4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
