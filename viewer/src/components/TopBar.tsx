import { forwardRef } from "react";
import { RecIndicator } from "./RecIndicator";
import { RecordingToggle } from "./RecordingToggle";
import { SearchBar } from "./SearchBar";

interface Props {
  live: boolean;
  search: string;
  onSearch: (v: string) => void;
  onClearSearch: () => void;
}

export const TopBar = forwardRef<HTMLInputElement, Props>(
  ({ live, search, onSearch, onClearSearch }, ref) => {
    return (
      <header className="flex items-center gap-6 border-b border-border bg-surface/60 px-5 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <RecIndicator live={live} />
          <span className="font-mono text-sm font-semibold tracking-tight text-ink">
            Flight&nbsp;Recorder
          </span>
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
