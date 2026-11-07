import type { HTMLAttributes, ReactNode } from "react";

const TONE_CHIP: Record<string, string> = {
  healthy: "border-healthy/30 bg-healthy/10 text-healthy",
  warning: "border-warning/30 bg-warning/10 text-warning",
  critical: "border-critical/30 bg-critical/10 text-critical",
  neutral: "border-white/10 bg-white/5 text-ink-dim",
  info: "border-info/30 bg-info/10 text-info",
};

export interface BadgeProps extends Omit<HTMLAttributes<HTMLSpanElement>, "children"> {
  tone?: keyof typeof TONE_CHIP;
  children: ReactNode;
}

/** Compact status chip; tone follows the health palette. */
export function Badge({ tone = "neutral", children, className = "", ...rest }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold tracking-[0.08em] uppercase ${TONE_CHIP[tone]} ${className}`}
      {...rest}
    >
      {children}
    </span>
  );
}

/** SIM / REAL provenance chip - required on every reading surface. */
export function SimBadge({ isSimulated, className = "" }: { isSimulated: boolean; className?: string }) {
  return (
    <Badge
      tone={isSimulated ? "info" : "healthy"}
      className={className}
      aria-label={isSimulated ? "Simulated data" : "Real sensor data"}
    >
      {isSimulated ? "Sim" : "Real"}
    </Badge>
  );
}
