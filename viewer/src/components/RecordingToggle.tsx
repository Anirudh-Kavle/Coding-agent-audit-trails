import { useEffect, useState } from "react";
import { dataSource } from "../lib/dataSource";

export function RecordingToggle() {
  const [paused, setPaused] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    dataSource.getRecordingPaused().then(setPaused).catch(() => setPaused(null));
  }, []);

  const toggle = async () => {
    if (paused === null || busy) return;
    const next = !paused;
    setBusy(true);
    setPaused(next); // optimistic
    try {
      const confirmed = await dataSource.setRecordingPaused(next);
      setPaused(confirmed);
    } catch {
      setPaused(!next); // revert on failure
    } finally {
      setBusy(false);
    }
  };

  if (paused === null) return null;

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      aria-pressed={!paused}
      title={paused ? "Recording paused — click to resume" : "Recording active — click to pause"}
      className={`inline-flex items-center gap-2 rounded-md border px-3 py-1.5 font-mono text-xs font-medium tracking-wide transition-colors disabled:opacity-60 ${
        paused
          ? "border-border text-ink-faint hover:text-ink"
          : "border-rec/40 text-rec hover:bg-rec/10"
      }`}
    >
      <span
        className={`h-2 w-2 rounded-full ${paused ? "bg-ink-faint" : "bg-rec fr-rec-dot"}`}
        aria-hidden
      />
      {paused ? "Paused" : "Recording"}
    </button>
  );
}
