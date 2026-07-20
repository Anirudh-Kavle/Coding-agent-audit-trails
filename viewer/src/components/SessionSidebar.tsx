import { useState } from "react";
import { type Session, type RiskTier, RISK_TIERS, RISK_DOT, RISK_LABEL } from "../types";
import { formatTime, dayLabel } from "../lib/format";

interface Props {
  sessions: Session[];
  selectedSession: string | null;
  onSelectSession: (id: string | null) => void;
  selectedProject: string | null; // a specific folder/clone (full path key)
  onSelectProject: (key: string | null) => void;
  selectedGroup: string | null; // a project name spanning all its folders
  onSelectGroup: (name: string | null) => void;
  riskFilter: Set<RiskTier>;
  onToggleRisk: (r: RiskTier) => void;
}

// Project identity is derived server-side (repo root, else working folder).
// Mock/legacy sessions without it fall back to cwd so grouping still works.
export function projectKeyOf(s: Session): string {
  return s.project_key ?? s.cwd ?? "unknown";
}

export function projectNameOf(s: Session): string {
  if (s.project) return s.project;
  const key = projectKeyOf(s);
  return key.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || "unknown";
}

const RISK_HINT: Record<RiskTier, string> = {
  info: "Read-only lookups: file reads, searches, listings",
  write: "File modifications: edits, writes, patches",
  exec: "Commands executed in a shell",
  network: "Actions that reached the network",
  sensitive: "Matched a sensitive pattern: credentials, secrets, or destructive commands",
};

// Disambiguating label for one folder/clone of a project: its last two path
// segments ("aleky/audit-trails-v2") — enough to tell versions apart without
// showing the whole path.
function variantLabel(key: string): string {
  const parts = key.replace(/[\\/]+$/, "").split(/[\\/]/).filter(Boolean);
  return parts.slice(-2).join("/") || key;
}

export function SessionSidebar({
  sessions,
  selectedSession,
  onSelectSession,
  selectedProject,
  onSelectProject,
  selectedGroup,
  onSelectGroup,
  riskFilter,
  onToggleRisk,
}: Props) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  // Two-level grouping: project name → folder/clone (full path) → sessions.
  // Two checkouts of the same project on one laptop share a name but differ
  // by path, so they appear as version sub-folders under one project.
  const groups = new Map<string, Map<string, Session[]>>();
  for (const s of sessions) {
    const name = projectNameOf(s);
    const key = projectKeyOf(s);
    const variants = groups.get(name) ?? new Map<string, Session[]>();
    variants.set(key, [...(variants.get(key) ?? []), s]);
    groups.set(name, variants);
  }

  const toggleCollapse = (key: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-surface/40">
      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-3">
        <SidebarHeading>Projects</SidebarHeading>
        <button
          onClick={() => {
            onSelectSession(null);
            onSelectProject(null);
            onSelectGroup(null);
          }}
          title="Show every recorded event across all projects and sessions"
          className={[
            "mb-2 block w-full cursor-pointer rounded px-2 py-1.5 text-left text-xs transition-colors",
            selectedSession === null && selectedProject === null && selectedGroup === null
              ? "bg-surface-2 text-ink"
              : "text-ink-muted hover:bg-surface/70 hover:text-ink",
          ].join(" ")}
        >
          All projects
        </button>

        {[...groups.entries()].map(([name, variants]) => {
          const isCollapsed = collapsed.has(name);
          const allSessions = [...variants.values()].flat();
          const isGroupSelected =
            selectedGroup === name && selectedSession === null && selectedProject === null;
          const live = allSessions.some((s) => s.live);
          const multiVariant = variants.size > 1;
          return (
            <div key={name} className="mb-2">
              <div
                className={[
                  "flex w-full items-center gap-1 rounded px-1 py-1 transition-colors",
                  isGroupSelected ? "bg-surface-2" : "hover:bg-surface/70",
                ].join(" ")}
              >
                <button
                  onClick={() => toggleCollapse(name)}
                  className="cursor-pointer p-0.5 text-ink-faint hover:text-ink"
                  aria-label={isCollapsed ? `Expand ${name}` : `Collapse ${name}`}
                  title={isCollapsed ? "Expand" : "Collapse"}
                >
                  <svg
                    className={`h-3 w-3 transition-transform ${isCollapsed ? "" : "rotate-90"}`}
                    viewBox="0 0 24 24"
                    fill="none"
                    aria-hidden
                  >
                    <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
                <button
                  onClick={() => {
                    onSelectGroup(name);
                    onSelectProject(null);
                    onSelectSession(null);
                  }}
                  className="flex min-w-0 flex-1 cursor-pointer items-center gap-1.5 text-left"
                  title={
                    multiVariant
                      ? `All ${variants.size} folders of "${name}" combined`
                      : [...variants.keys()][0]
                  }
                >
                  <span
                    className={`h-1.5 w-1.5 shrink-0 rounded-full ${live ? "bg-rec fr-rec-dot" : "bg-ink-faint"}`}
                    aria-hidden
                  />
                  <span className="truncate text-xs font-medium text-ink">{name}</span>
                  <span className="ml-auto shrink-0 font-mono text-[10px] text-ink-faint">
                    {allSessions.length}
                  </span>
                </button>
              </div>

              {!isCollapsed &&
                [...variants.entries()].map(([key, list]) => (
                  <div key={key}>
                    {/* Folder sub-level only when the project exists in more
                        than one place (e.g. two versions/clones). */}
                    {multiVariant && (
                      <button
                        onClick={() => {
                          onSelectProject(key);
                          onSelectGroup(null);
                          onSelectSession(null);
                        }}
                        title={key}
                        className={[
                          "flex w-full cursor-pointer items-center gap-1.5 rounded py-1 pl-5 pr-2 text-left transition-colors",
                          selectedProject === key && selectedSession === null
                            ? "bg-surface-2"
                            : "hover:bg-surface/70",
                        ].join(" ")}
                      >
                        <FolderIcon />
                        <span className="truncate font-mono text-[10px] text-ink-muted">
                          {variantLabel(key)}
                        </span>
                        <span className="ml-auto shrink-0 font-mono text-[10px] text-ink-faint">
                          {list.length}
                        </span>
                      </button>
                    )}
                    {list.map((s) => (
                      <button
                        key={s.id}
                        onClick={() => {
                          onSelectSession(s.id);
                          onSelectProject(null);
                          onSelectGroup(null);
                        }}
                        title={`Session ${s.id}\nFolder: ${s.cwd}`}
                        className={[
                          "block w-full cursor-pointer rounded py-1 pr-2 text-left transition-colors",
                          multiVariant ? "pl-8" : "pl-6",
                          selectedSession === s.id ? "bg-surface-2" : "hover:bg-surface/70",
                        ].join(" ")}
                      >
                        <span className="flex items-center gap-2">
                          <span
                            className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                              s.live ? "bg-rec fr-rec-dot" : "bg-ink-faint"
                            }`}
                            title={s.live ? "Still recording" : "Session ended"}
                            aria-hidden
                          />
                          <span className="shrink-0 font-mono text-[10px] text-ink-faint">
                            {dayLabel(s.started_at)} {formatTime(s.started_at).slice(0, 5)}
                          </span>
                          <span className="truncate font-mono text-[10px] text-ink-muted">
                            {s.label ?? s.id.slice(0, 8)}
                          </span>
                        </span>
                      </button>
                    ))}
                  </div>
                ))}
            </div>
          );
        })}
      </div>

      {/* Risk filters */}
      <div className="border-t border-border px-3 py-3">
        <SidebarHeading>Filters</SidebarHeading>
        <div className="mt-1 space-y-1">
          {RISK_TIERS.map((r) => {
            const on = riskFilter.has(r);
            return (
              <label
                key={r}
                title={RISK_HINT[r]}
                className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-xs transition-colors hover:bg-surface/70"
              >
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() => onToggleRisk(r)}
                  className="peer sr-only"
                />
                <span
                  className={[
                    "flex h-3.5 w-3.5 items-center justify-center rounded-sm border",
                    on ? "border-transparent" : "border-border",
                    on ? RISK_DOT[r] : "",
                  ].join(" ")}
                  aria-hidden
                >
                  {on && (
                    <svg className="h-2.5 w-2.5 text-bg" viewBox="0 0 24 24" fill="none">
                      <path d="M5 12l5 5L20 7" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </span>
                <span className={on ? "text-ink" : "text-ink-muted"}>{RISK_LABEL[r]}</span>
              </label>
            );
          })}
        </div>
      </div>
    </aside>
  );
}

function FolderIcon() {
  return (
    <svg className="h-3 w-3 shrink-0 text-ink-faint" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"
        stroke="currentColor"
        strokeWidth="2"
      />
    </svg>
  );
}

function SidebarHeading({ children }: { children: React.ReactNode }) {
  return (
    <p className="px-2 pb-1 font-mono text-[10px] uppercase tracking-wider text-ink-faint">
      {children}
    </p>
  );
}
