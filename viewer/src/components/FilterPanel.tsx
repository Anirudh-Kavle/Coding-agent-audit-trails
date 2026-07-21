import type { ReactNode } from "react";
import type { Session } from "../types";
import { RISK_TIERS, RISK_DOT, RISK_LABEL, type RiskTier } from "../types";
import { parseQuery } from "../lib/search";
import { toolCatalogFor, type ToolTag, type ToolKind, type Provider } from "../lib/agents";
import { dayLabel } from "../lib/format";

// Sentinel written when a facet's checkbox list is deliberately emptied
// (0 checked). An empty qualifier value ("risk:") parses to a falsy string,
// which filterEvents reads as "no filter" — the opposite of what 0-checked
// means. This value never matches any real risk tier / tool name / session
// id, so it correctly filters out everything for that facet instead.
const NONE = "__none__";

function tagToken(tag: ToolTag): string {
  return tag.prefix ? `${tag.prefix}*` : tag.names.join("+");
}

// Kind groups shown in the Tool column, in display order. Grouping by kind
// (rather than one row per raw tool name) keeps the column scannable even
// though the underlying catalog now has dozens of tools per agent.
const KIND_GROUP_ORDER: { key: string; kinds: ToolKind[] }[] = [
  { key: "bash", kinds: ["bash"] },
  { key: "editwrite", kinds: ["edit", "write"] },
  { key: "read", kinds: ["read"] },
  { key: "webfetch", kinds: ["webfetch"] },
  { key: "mcp", kinds: ["mcp"] },
  { key: "other", kinds: ["other"] },
];

interface ToolGroup {
  key: string;
  label: string;
  risk: RiskTier;
  tags: ToolTag[];
}

function buildToolGroups(catalog: ToolTag[]): ToolGroup[] {
  const groups: ToolGroup[] = [];
  for (const { key, kinds } of KIND_GROUP_ORDER) {
    const tags = catalog.filter((t) => kinds.includes(t.kind));
    if (tags.length === 0) continue;
    const label = key === "mcp" ? "MCP" : key === "other" ? `Other (${tags.length})` : tags.map((t) => t.tool).join(" / ");
    groups.push({ key, label, risk: tags[0].risk, tags });
  }
  return groups;
}

interface Props {
  value: string;
  onChange: (v: string) => void;
  sessions: Session[];
  agentFilter: Provider | null;
}

// Docked filter panel for the search bar — Risk / Tool / Session laid out as
// three flat columns, always visible (no per-section collapse). Every
// control here writes straight into the same qualifier syntax
// (tool:bash risk:sensitive) that a power user could type by hand, so the
// text field stays the single source of truth. The Tool column is scoped to
// whichever Agent is selected in the sidebar — selecting Claude shows only
// Claude's tools, never Codex's or the API agent's. File filtering has no
// dedicated column here; type `file:` directly in the search box for that.
export function FilterPanel({ value, onChange, sessions, agentFilter }: Props) {
  const toolCatalog = toolCatalogFor(agentFilter);
  const toolGroups = buildToolGroups(toolCatalog);
  const parsed = parseQuery(value);

  const withoutQualifier = (q: string) =>
    value
      .split(/\s+/)
      .filter(Boolean)
      .filter((t) => !t.startsWith(`${q}:`))
      .join(" ");

  // tokens === null clears the qualifier entirely (the "everything selected /
  // default" state); an empty array writes the NONE sentinel instead of
  // clearing, since 0 selected means "match nothing", not "no filter".
  const setQualifier = (q: string, tokens: string[] | null) => {
    const rest = withoutQualifier(q);
    if (tokens === null) {
      onChange(rest);
      return;
    }
    const joined = `${q}:${tokens.length ? tokens.join(",") : NONE}`;
    onChange(rest ? `${rest} ${joined}` : joined);
  };

  // --- Risk ---
  const riskChecked = new Set<RiskTier>(
    parsed.risk
      ? parsed.risk.split(",").filter((r): r is RiskTier => (RISK_TIERS as string[]).includes(r))
      : RISK_TIERS
  );
  const toggleRisk = (tier: RiskTier) => {
    const next = new Set(riskChecked);
    if (next.has(tier)) next.delete(tier);
    else next.add(tier);
    setQualifier("risk", next.size === RISK_TIERS.length ? null : [...next]);
  };

  // --- Tool ---
  const toolTokens = parsed.tool ? parsed.tool.split(",").flatMap((t) => t.split("+")) : null;
  const isToolChecked = (tag: ToolTag) => {
    if (!toolTokens) return true;
    const own = tag.prefix ? [`${tag.prefix}*`] : tag.names;
    return own.every((n) => toolTokens.includes(n));
  };
  const isGroupChecked = (g: ToolGroup) => g.tags.every(isToolChecked);
  const toggleGroup = (g: ToolGroup) => {
    const turningOn = !isGroupChecked(g);
    const groupIds = new Set(g.tags.map((t) => t.id));
    const nextChecked = toolCatalog.filter((t) => (groupIds.has(t.id) ? turningOn : isToolChecked(t)));
    if (nextChecked.length === toolCatalog.length) setQualifier("tool", null);
    else setQualifier("tool", nextChecked.map(tagToken));
  };

  // --- Session --- (just the two quick presets — no per-session id list)
  const sessionTokens = parsed.session ? parsed.session.split(",") : null;
  const todayIds = sessions.filter((s) => dayLabel(s.started_at) === "today").map((s) => s.id.toLowerCase());
  const allSelected = sessionTokens === null;
  const todaySelected =
    sessionTokens !== null &&
    sessionTokens.length === todayIds.length &&
    todayIds.every((id) => sessionTokens.includes(id));
  const selectAllSessions = () => setQualifier("session", null);
  const selectTodaySessions = () => setQualifier("session", todayIds.length ? todayIds : []);

  // --- Select all / Clear all, across every facet at once ---
  const clearQualifiers = (qs: string[]) =>
    qs.reduce(
      (v, q) => v.split(/\s+/).filter(Boolean).filter((t) => !t.startsWith(`${q}:`)).join(" "),
      value
    );
  const selectAllFilters = () => onChange(clearQualifiers(["risk", "tool", "session"]));
  const clearAllFilters = () => {
    const rest = clearQualifiers(["risk", "tool", "session"]);
    const tokens = ["risk", "tool", "session"].map((q) => `${q}:${NONE}`).join(" ");
    onChange(rest ? `${rest} ${tokens}` : tokens);
  };

  return (
    <div className="absolute left-0 top-full z-40 mt-2 w-full rounded-lg border border-border bg-surface-2 shadow-2xl">
      <div className="flex items-center justify-end gap-2 border-b border-border-soft px-4 py-2">
        <button
          type="button"
          onClick={selectAllFilters}
          className="cursor-pointer rounded border border-border-soft bg-surface px-2.5 py-1 font-mono text-xs text-ink-muted transition-colors hover:border-border hover:text-ink"
        >
          Select all
        </button>
        <button
          type="button"
          onClick={clearAllFilters}
          className="cursor-pointer rounded border border-border-soft bg-surface px-2.5 py-1 font-mono text-xs text-ink-muted transition-colors hover:border-border hover:text-ink"
        >
          Clear all
        </button>
      </div>
      <div className="grid grid-cols-3 gap-6 px-4 py-3">
        <Column title="Risk">
          {RISK_TIERS.map((r) => (
            <CheckRow
              key={r}
              checked={riskChecked.has(r)}
              onChange={() => toggleRisk(r)}
              dotClass={RISK_DOT[r]}
              label={RISK_LABEL[r]}
            />
          ))}
        </Column>

        <Column title="Tool">
          <div className="max-h-56 space-y-1 overflow-y-auto pr-1">
            {toolGroups.map((g) => (
              <CheckRow
                key={g.key}
                checked={isGroupChecked(g)}
                onChange={() => toggleGroup(g)}
                dotClass={RISK_DOT[g.risk]}
                label={g.label}
                truncate
              />
            ))}
          </div>
        </Column>

        <Column title="Session">
          <CheckRow checked={allSelected} onChange={selectAllSessions} label="all sessions" bold={allSelected} />
          <CheckRow checked={todaySelected} onChange={selectTodaySessions} label="today only" bold={todaySelected} />
        </Column>
      </div>
    </div>
  );
}

function Column({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="mb-2 font-sans text-xs font-medium uppercase tracking-wide text-ink-muted">{title}</p>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function CheckRow({
  checked,
  onChange,
  label,
  dotClass,
  bold = false,
  truncate = false,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
  dotClass?: string;
  bold?: boolean;
  truncate?: boolean;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-xs transition-colors hover:bg-surface/70">
      <input type="checkbox" checked={checked} onChange={onChange} className="peer sr-only" />
      <span
        className={[
          "flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-sm border",
          checked ? `border-transparent ${dotClass ?? "bg-ink-muted"}` : "border-border",
        ].join(" ")}
        aria-hidden
      >
        {checked && (
          <svg className="h-2.5 w-2.5 text-bg" viewBox="0 0 24 24" fill="none">
            <path d="M5 12l5 5L20 7" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </span>
      <span
        className={[
          "font-mono",
          truncate ? "truncate" : "",
          bold ? "font-semibold" : "",
          checked ? "text-ink" : "text-ink-muted",
        ].join(" ")}
      >
        {label}
      </span>
    </label>
  );
}
