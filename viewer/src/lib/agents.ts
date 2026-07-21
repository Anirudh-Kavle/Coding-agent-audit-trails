import type { RiskTier } from "../types";

// The three hook sources events/sessions can come from. "unknown" covers rows
// recorded before the `provider` column existed on events.
export type Provider = "claude" | "codex" | "openai-api" | "unknown";
export type KnownProvider = Exclude<Provider, "unknown">;

export const PROVIDERS: KnownProvider[] = ["claude", "codex", "openai-api"];

export const PROVIDER_LABEL: Record<Provider, string> = {
  claude: "Claude Code",
  codex: "Codex",
  "openai-api": "API Agent",
  unknown: "Other",
};

export const PROVIDER_SHORT: Record<Provider, string> = {
  claude: "Claude",
  codex: "Codex",
  "openai-api": "API",
  unknown: "Other",
};

export const PROVIDER_DESCRIPTION: Record<Provider, string> = {
  claude: "Claude Code CLI sessions.",
  codex: "OpenAI Codex CLI sessions.",
  "openai-api": "The bundled fr api-ui terminal agent.",
  unknown: "Provider not recorded on this event.",
};

// tools.py's action_kind() categories — the "recorded category" column,
// independent of risk tier. Exposed alongside risk in the tooltip so the two
// are never conflated (a tool's category does NOT determine its risk tier;
// only risk_rules.yaml's tool_tiers lookup by exact raw tool name does).
export type ToolKind = "bash" | "read" | "write" | "edit" | "webfetch" | "mcp" | "other";

// One filter "tag" per raw tool name (or family of names) a provider's hook
// actually emits. `risk` is the tier risk.classify() actually assigns at
// baseline (risk_rules.yaml `tool_tiers`, keyed on the *exact* raw tool name
// it hands over — unmatched names fall through to `default_tier: exec`); a
// specific call can still escalate to "sensitive" via a pattern match on its
// arguments. `names` match FlightEvent.tool case-insensitively; `prefix`
// additionally matches by prefix (for mcp__*).
export interface ToolTag {
  id: string;
  tool: string; // display label
  kind: ToolKind;
  risk: RiskTier;
  description: string;
  names: string[];
  prefix?: string;
}

// The catalog is intentionally NOT the same list for every agent — Claude,
// Codex, and the API agent each report a different raw tool vocabulary, and
// the filter panel is meant to show exactly that agent's tags, not a
// lowest-common-denominator union.
export const PROVIDER_TOOLS: Record<KnownProvider, ToolTag[]> = {
  // Full built-in tool list per Claude Code's official tools reference
  // (code.claude.com/docs/en/tools-reference), verified 2026-07. Only Read,
  // Glob, Grep, LS, Edit, Write, NotebookEdit, Bash, WebFetch, WebSearch are
  // keyed in risk_rules.yaml's tool_tiers; every other tool here is real and
  // in active use but isn't in that table, so risk.classify() falls it
  // through to `default_tier: exec`, and tools.py's action_kind() doesn't
  // match its name to a category either, so kind is "other" — both fields
  // reflect actual current backend behavior, not a placeholder.
  claude: [
    { id: "claude:read", tool: "Read", kind: "read", risk: "info", description: "Reads the contents of files.", names: ["read"] },
    { id: "claude:glob", tool: "Glob", kind: "read", risk: "info", description: "Finds files based on pattern matching.", names: ["glob"] },
    { id: "claude:grep", tool: "Grep", kind: "read", risk: "info", description: "Searches for patterns in file contents.", names: ["grep"] },
    { id: "claude:ls", tool: "LS", kind: "read", risk: "info", description: "Lists a directory's contents.", names: ["ls"] },
    { id: "claude:edit", tool: "Edit", kind: "edit", risk: "write", description: "Makes targeted edits to specific files.", names: ["edit"] },
    { id: "claude:write", tool: "Write", kind: "write", risk: "write", description: "Creates or overwrites files.", names: ["write"] },
    { id: "claude:notebookedit", tool: "NotebookEdit", kind: "edit", risk: "write", description: "Modifies Jupyter notebook cells.", names: ["notebookedit"] },
    { id: "claude:bash", tool: "Bash", kind: "bash", risk: "exec", description: "Executes shell commands in your environment.", names: ["bash"] },
    { id: "claude:powershell", tool: "PowerShell", kind: "other", risk: "exec", description: "Executes PowerShell commands natively.", names: ["powershell"] },
    { id: "claude:webfetch", tool: "WebFetch", kind: "webfetch", risk: "network", description: "Fetches content from a specified URL.", names: ["webfetch"] },
    { id: "claude:websearch", tool: "WebSearch", kind: "webfetch", risk: "network", description: "Performs web searches.", names: ["websearch"] },
    { id: "claude:agent", tool: "Agent", kind: "other", risk: "exec", description: "Spawns a subagent with its own context window to handle a task.", names: ["agent"] },
    { id: "claude:skill", tool: "Skill", kind: "other", risk: "exec", description: "Executes a skill within the main conversation.", names: ["skill"] },
    { id: "claude:workflow", tool: "Workflow", kind: "other", risk: "exec", description: "Runs a dynamic workflow orchestrating subagents in the background.", names: ["workflow"] },
    { id: "claude:todowrite", tool: "TodoWrite", kind: "other", risk: "exec", description: "Manages the session task checklist (legacy, off by default).", names: ["todowrite"] },
    { id: "claude:taskcreate", tool: "TaskCreate", kind: "other", risk: "exec", description: "Creates a new task in the task list.", names: ["taskcreate"] },
    { id: "claude:taskget", tool: "TaskGet", kind: "other", risk: "exec", description: "Retrieves full details for a specific task.", names: ["taskget"] },
    { id: "claude:tasklist", tool: "TaskList", kind: "other", risk: "exec", description: "Lists all tasks with their current status.", names: ["tasklist"] },
    { id: "claude:taskupdate", tool: "TaskUpdate", kind: "other", risk: "exec", description: "Updates task status, dependencies, or details.", names: ["taskupdate"] },
    { id: "claude:taskoutput", tool: "TaskOutput", kind: "other", risk: "exec", description: "Retrieves output from a background task.", names: ["taskoutput"] },
    { id: "claude:taskstop", tool: "TaskStop", kind: "other", risk: "exec", description: "Stops a running background task by ID.", names: ["taskstop"] },
    { id: "claude:enterplanmode", tool: "EnterPlanMode", kind: "other", risk: "exec", description: "Switches to plan mode to design an approach before coding.", names: ["enterplanmode"] },
    { id: "claude:exitplanmode", tool: "ExitPlanMode", kind: "other", risk: "exec", description: "Presents a plan for approval and exits plan mode.", names: ["exitplanmode"] },
    { id: "claude:enterworktree", tool: "EnterWorktree", kind: "other", risk: "exec", description: "Creates an isolated git worktree and switches into it.", names: ["enterworktree"] },
    { id: "claude:exitworktree", tool: "ExitWorktree", kind: "other", risk: "exec", description: "Exits a worktree session and returns to the original directory.", names: ["exitworktree"] },
    { id: "claude:monitor", tool: "Monitor", kind: "other", risk: "exec", description: "Runs a command in the background and streams output lines back.", names: ["monitor"] },
    { id: "claude:lsp", tool: "LSP", kind: "other", risk: "exec", description: "Code intelligence via language servers (definitions, references, diagnostics).", names: ["lsp"] },
    { id: "claude:artifact", tool: "Artifact", kind: "other", risk: "exec", description: "Publishes an HTML or Markdown file as a claude.ai artifact.", names: ["artifact"] },
    { id: "claude:askuserquestion", tool: "AskUserQuestion", kind: "other", risk: "exec", description: "Asks multiple-choice questions to gather requirements or clarify ambiguity.", names: ["askuserquestion"] },
    { id: "claude:endconversation", tool: "EndConversation", kind: "other", risk: "exec", description: "Ends the session (sustained abuse, or on explicit request to demo it).", names: ["endconversation"] },
    { id: "claude:crontcreate", tool: "CronCreate", kind: "other", risk: "exec", description: "Schedules a recurring or one-shot prompt within the session.", names: ["croncreate"] },
    { id: "claude:crondelete", tool: "CronDelete", kind: "other", risk: "exec", description: "Cancels a scheduled task by ID.", names: ["crondelete"] },
    { id: "claude:cronlist", tool: "CronList", kind: "other", risk: "exec", description: "Lists all scheduled tasks in the session.", names: ["cronlist"] },
    { id: "claude:schedulewakeup", tool: "ScheduleWakeup", kind: "other", risk: "exec", description: "Reschedules the next iteration of a self-paced /loop.", names: ["schedulewakeup"] },
    { id: "claude:sendmessage", tool: "SendMessage", kind: "other", risk: "exec", description: "Sends a message to an agent-team teammate or resumes a subagent.", names: ["sendmessage"] },
    { id: "claude:senduserfile", tool: "SendUserFile", kind: "other", risk: "exec", description: "Sends a session file to you (report, diagram, screenshot, build output).", names: ["senduserfile"] },
    { id: "claude:pushnotification", tool: "PushNotification", kind: "other", risk: "exec", description: "Sends a desktop/phone notification when you've stepped away.", names: ["pushnotification"] },
    { id: "claude:remotetrigger", tool: "RemoteTrigger", kind: "other", risk: "exec", description: "Creates, updates, runs, and lists Routines on claude.ai.", names: ["remotetrigger"] },
    { id: "claude:reportfindings", tool: "ReportFindings", kind: "other", risk: "exec", description: "Reports code-review findings as a structured list.", names: ["reportfindings"] },
    { id: "claude:shareonboardingguide", tool: "ShareOnboardingGuide", kind: "other", risk: "exec", description: "Uploads ONBOARDING.md and returns a share link for teammates.", names: ["shareonboardingguide"] },
    { id: "claude:listmcpresourcestool", tool: "ListMcpResourcesTool", kind: "other", risk: "exec", description: "Lists resources exposed by connected MCP servers.", names: ["listmcpresourcestool"] },
    { id: "claude:readmcpresourcetool", tool: "ReadMcpResourceTool", kind: "other", risk: "exec", description: "Reads a specific MCP resource by URI.", names: ["readmcpresourcetool"] },
    { id: "claude:waitformcpservers", tool: "WaitForMcpServers", kind: "other", risk: "exec", description: "Waits for MCP servers still connecting in the background.", names: ["waitformcpservers"] },
    { id: "claude:toolsearch", tool: "ToolSearch", kind: "other", risk: "exec", description: "Searches for and loads deferred MCP tools.", names: ["toolsearch"] },
    { id: "claude:mcp", tool: "mcp__*", kind: "mcp", risk: "exec", description: "Calls a tool exposed by an MCP server.", names: [], prefix: "mcp__" },
  ],
  // Verified against openai/codex (github.com/openai/codex) docs and the
  // OpenAI developer changelog, 2026-07. shell/run_command/Bash are all
  // observed aliases for the same exec tool across Codex versions.
  codex: [
    { id: "codex:bash", tool: "Bash / run_command / shell", kind: "bash", risk: "exec", description: "Runs a shell command or unified-exec call.", names: ["bash", "run_command", "shell"] },
    { id: "codex:apply_patch", tool: "apply_patch", kind: "edit", risk: "write", description: "Adds, updates, or deletes a file via a unified patch.", names: ["apply_patch"] },
    { id: "codex:update_plan", tool: "update_plan", kind: "other", risk: "info", description: "Updates Codex's internal task plan — no filesystem/shell effect.", names: ["update_plan"] },
    { id: "codex:view_image", tool: "view_image", kind: "read", risk: "info", description: "Views an image file.", names: ["view_image"] },
    { id: "codex:web_search", tool: "web_search", kind: "webfetch", risk: "exec", description: "Runs a web search when Codex's web-search option is enabled.", names: ["web_search"] },
    { id: "codex:multi_tool_use", tool: "multi_tool_use", kind: "other", risk: "exec", description: "Wraps several parallel tool calls issued in one turn.", names: ["multi_tool_use"] },
    { id: "codex:mcp", tool: "mcp__*", kind: "mcp", risk: "exec", description: "Calls a tool exposed by an MCP server.", names: [], prefix: "mcp__" },
  ],
  // The bundled `fr api-ui` agent (flight_recorder/agent.py TOOLS) — only
  // these four tools are wired up today; WebSearch/file-search/code
  // interpreter/MCP are not in its TOOLS list. Every call also carries a
  // required, visible `reason` argument (captured as the event's WHY).
  // risk.classify() keys tool_tiers by the *exact* raw name the hook passes —
  // these lowercase names (list_files, read_file, write_file, run_command)
  // don't match any tool_tiers entry (which uses Claude/Codex-style names),
  // so all four fall through to `default_tier: exec` regardless of category,
  // then escalate to "sensitive" per-call if the args match a risk pattern.
  "openai-api": [
    { id: "api:list_files", tool: "list_files", kind: "read", risk: "exec", description: "Lists files or directories under a path.", names: ["list_files"] },
    { id: "api:read_file", tool: "read_file", kind: "read", risk: "exec", description: "Reads a UTF-8 text file.", names: ["read_file"] },
    { id: "api:write_file", tool: "write_file", kind: "write", risk: "exec", description: "Creates or replaces a UTF-8 text file.", names: ["write_file"] },
    { id: "api:run_command", tool: "run_command", kind: "bash", risk: "exec", description: "Runs a shell command in the project root.", names: ["run_command"] },
  ],
};

// Merge every provider's tags for a tier when no specific agent is selected
// (used by the risk-filter tooltips to list example tools per tier).
export function toolsForTier(tier: RiskTier, provider: Provider | null): ToolTag[] {
  const providers: KnownProvider[] = provider && provider !== "unknown" ? [provider] : ["claude", "codex", "openai-api"];
  return providers.flatMap((p) => PROVIDER_TOOLS[p].filter((t) => t.risk === tier));
}

// The Tool filter's catalog, scoped to whichever Agent is selected (sidebar
// agentFilter) — selecting Claude must show only Claude's own tool
// vocabulary, not Codex's or the API agent's. With no agent selected, every
// provider's tools are shown together.
export function toolCatalogFor(provider: Provider | null): ToolTag[] {
  if (provider && provider !== "unknown") return PROVIDER_TOOLS[provider];
  return [...PROVIDER_TOOLS.claude, ...PROVIDER_TOOLS.codex, ...PROVIDER_TOOLS["openai-api"]];
}
