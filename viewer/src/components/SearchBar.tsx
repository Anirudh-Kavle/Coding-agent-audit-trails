import { forwardRef } from "react";
import { RISK_TIERS } from "../types";
import { activeQualifier, SEARCH_QUALIFIERS } from "../lib/search";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onClear: () => void;
}

// One box + qualifier chips (spec 4.2). Chips append `qualifier:`; when a qualifier
// is active, its value options appear. Esc-to-clear is handled globally.
export const SearchBar = forwardRef<HTMLInputElement, Props>(
  ({ value, onChange, onClear }, ref) => {
    const active = activeQualifier(value);
    const append = (frag: string) => {
      const sep = value && !value.endsWith(" ") && !value.endsWith(":") ? " " : "";
      onChange(value + sep + frag);
    };

    return (
      <div className="relative w-full max-w-xl">
        <div className="flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5">
          <SearchIcon />
          <input
            ref={ref}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="search all sessions   tool:bash risk:sensitive exit:fail after:2026-07-01"
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

        {/* Chip hints — value options for an active qualifier, else the qualifier set. */}
        <div className="mt-2 flex flex-wrap gap-1.5">
          {active === "risk"
            ? RISK_TIERS.map((r) => (
                <Chip key={r} onClick={() => append(r + " ")}>
                  {r}
                </Chip>
              ))
            : !active &&
              SEARCH_QUALIFIERS.map((q) => (
                <Chip key={q} onClick={() => append(q + ":")}>
                  {q}:
                </Chip>
              ))}
        </div>
      </div>
    );
  }
);
SearchBar.displayName = "SearchBar";

function Chip({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="cursor-pointer rounded border border-border-soft bg-surface-2 px-2 py-0.5 font-mono text-xs text-ink-muted transition-colors hover:border-border hover:text-ink"
    >
      {children}
    </button>
  );
}

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
