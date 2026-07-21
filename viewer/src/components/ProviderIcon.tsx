import type { KnownProvider } from "../lib/agents";

// Brand-inspired marks for the Agent filter. Claude's is Anthropic's asterisk
// sunburst; Codex's is OpenAI's hex-flower knot (Codex is an OpenAI product) —
// both are simplified redraws, not the official brand asset files. The API
// agent has no real-world brand of its own (it's this project's own bundled
// `fr api-ui` script, not a distinct product), so it gets a neutral bolt mark
// instead of a fabricated logo. All use currentColor to follow the button's
// active/inactive text color.
export function ProviderIcon({ provider, className = "h-3 w-3" }: { provider: KnownProvider; className?: string }) {
  switch (provider) {
    case "claude":
      // Twelve-ray sunburst with a thick blobby center and blunt, alternating
      // ray lengths — redrawn from the reference asset the user supplied,
      // not the official file itself.
      return (
        <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
          {[0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330].map((deg, i) => (
            <line
              key={deg}
              x1="12"
              y1="12"
              x2="12"
              y2={i % 2 === 0 ? "1.6" : "3.4"}
              transform={`rotate(${deg} 12 12)`}
              stroke="currentColor"
              strokeWidth="2.6"
              strokeLinecap="round"
            />
          ))}
          <circle cx="12" cy="12" r="3.6" fill="currentColor" />
        </svg>
      );
    case "codex":
      // OpenAI's hex-flower knot — the standard public mark for "built on OpenAI".
      return (
        <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <path d="M22.28 9.82a5.98 5.98 0 0 0-.51-4.91 6.05 6.05 0 0 0-6.51-2.9A6.07 6.07 0 0 0 4.98 4.18a5.98 5.98 0 0 0-4 2.9 6.05 6.05 0 0 0 .74 7.1 5.98 5.98 0 0 0 .51 4.9 6.05 6.05 0 0 0 6.52 2.9A5.98 5.98 0 0 0 13.26 24a6.06 6.06 0 0 0 5.77-4.2 5.99 5.99 0 0 0 4-2.9 6.06 6.06 0 0 0-.75-7.08zM13.26 22.4a4.48 4.48 0 0 1-2.88-1.04l.14-.08 4.78-2.76a.79.79 0 0 0 .39-.68v-6.74l2.02 1.17a.07.07 0 0 1 .04.05v5.58a4.5 4.5 0 0 1-4.49 4.5zM3.6 18.28a4.47 4.47 0 0 1-.54-3.02l.14.09 4.78 2.76a.77.77 0 0 0 .78 0l5.84-3.37v2.33a.08.08 0 0 1-.03.07l-4.83 2.78a4.5 4.5 0 0 1-6.14-1.64zM2.34 7.9A4.49 4.49 0 0 1 4.7 5.92V11.6a.77.77 0 0 0 .39.68l5.81 3.35-2.02 1.17a.08.08 0 0 1-.07 0L3.99 14a4.5 4.5 0 0 1-1.66-6.11zm16.6 3.86-5.84-3.39 2.02-1.16a.08.08 0 0 1 .07 0l4.83 2.79a4.49 4.49 0 0 1-.68 8.1v-5.68a.79.79 0 0 0-.4-.66zm2.01-3.02-.14-.09-4.78-2.78a.78.78 0 0 0-.78 0L9.4 9.23V6.9a.07.07 0 0 1 .03-.06l4.83-2.79a4.5 4.5 0 0 1 6.68 4.66zM8.3 12.86l-2.02-1.16a.08.08 0 0 1-.04-.06V6.07a4.5 4.5 0 0 1 7.38-3.45l-.14.08-4.78 2.76a.79.79 0 0 0-.4.68zm1.1-2.37 2.6-1.5 2.6 1.5v3l-2.6 1.5-2.6-1.5z" />
        </svg>
      );
    case "openai-api":
      return (
        <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
          <path
            d="M13.5 3 6 12h5l-1.5 9L18 12h-5l1.5-9Z"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
  }
}
