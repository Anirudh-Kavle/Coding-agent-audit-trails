import { type RiskTier, RISK_DOT, RISK_TEXT, RISK_LABEL } from "../types";

// Risk shown as dot + text label — color is NEVER the only signal (colorblind safety).
export function RiskBadge({ risk, size = "sm" }: { risk: RiskTier; size?: "sm" | "xs" }) {
  const dot = size === "xs" ? "h-1.5 w-1.5" : "h-2 w-2";
  const text = size === "xs" ? "text-[10px]" : "text-xs";
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`${dot} rounded-full ${RISK_DOT[risk]}`} aria-hidden />
      <span className={`${text} font-mono uppercase tracking-wide ${RISK_TEXT[risk]}`}>
        {RISK_LABEL[risk]}
      </span>
    </span>
  );
}
