import type { ReactNode } from "react";

interface Props {
  label: string;
  children: ReactNode;
  className?: string;
}

// Hover-only detail popover. Native `title` can't be styled to match the
// black-box theme and clips at OS-defined wrap widths, so this is a small
// CSS-only (group-hover) stand-in used for filter descriptions.
export function Tooltip({ label, children, className }: Props) {
  return (
    <span className={`group/tip relative ${className ?? "inline-flex"}`}>
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-full z-50 mt-2 max-w-56 -translate-x-1/2 whitespace-normal break-words rounded-md border border-border bg-surface-2 px-2.5 py-1.5 text-[11px] leading-snug text-ink-muted opacity-0 shadow-2xl transition-opacity delay-150 duration-100 group-hover/tip:opacity-100"
      >
        {label}
      </span>
    </span>
  );
}
