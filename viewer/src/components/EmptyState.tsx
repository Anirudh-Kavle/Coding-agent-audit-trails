// Zero-state teaches the three commands to get recording (spec 4.1).
export function EmptyState({ mode }: { mode: "no-events" | "no-results" }) {
  if (mode === "no-results") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-10 text-center">
        <p className="text-sm text-ink-muted">No actions match this search.</p>
        <p className="font-mono text-xs text-ink-faint">Press Esc to return to the live timeline.</p>
      </div>
    );
  }

  const steps = [
    { cmd: "fr init", note: "install the hooks into .claude/settings.json" },
    { cmd: "claude", note: "start a session and do some work" },
    { cmd: "watch here", note: "actions stream in, live" },
  ];

  return (
    <div className="flex h-full flex-col items-center justify-center gap-6 p-10 text-center">
      <div>
        <p className="text-base font-medium text-ink">Nothing recorded yet.</p>
        <p className="mt-1 text-sm text-ink-muted">
          Flight Recorder captures every action your agent takes — and why.
        </p>
      </div>
      <ol className="flex flex-col gap-3 text-left">
        {steps.map((s, i) => (
          <li key={s.cmd} className="flex items-center gap-3">
            <span className="flex h-6 w-6 items-center justify-center rounded-full border border-border font-mono text-xs text-ink-muted">
              {i + 1}
            </span>
            <code className="rounded bg-surface-2 px-2 py-1 font-mono text-sm text-ink">
              {s.cmd}
            </code>
            <span className="text-xs text-ink-faint">{s.note}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
