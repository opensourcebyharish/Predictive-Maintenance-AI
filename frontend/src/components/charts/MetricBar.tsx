import { motion } from "framer-motion";

import { formatPercent } from "@/lib/format";

/**
 * Horizontal 0-1 capacity bar with threshold ticks (0.5 elevated, 0.8 critical)
 * for anomaly scores and failure probabilities.
 */
export function MetricBar({
  value,
  thresholds = [0.5, 0.8],
  color,
  label,
  caption,
  display,
  ariaLabel,
}: {
  value: number | null | undefined;
  thresholds?: number[];
  color: string;
  label: string;
  caption?: string;
  display?: string;
  ariaLabel?: string;
}) {
  const clamped = value === null || value === undefined || !Number.isFinite(value) ? null : Math.min(1, Math.max(0, value));
  return (
    <div aria-label={ariaLabel ?? label} role="img">
      <div className="flex items-baseline justify-between text-xs">
        <span className="font-medium tracking-wide text-ink-dim uppercase">{label}</span>
        <span className={`tnum font-semibold ${clamped === null ? "text-ink-faint" : ""}`} style={clamped === null ? undefined : { color }}>
          {display ?? (clamped === null ? "—" : formatPercent(clamped))}
        </span>
      </div>
      <div className="relative mt-1.5 h-2 overflow-hidden rounded-full bg-white/6">
        {clamped !== null && (
          <motion.div
            className="absolute inset-y-0 left-0 rounded-full"
            style={{ backgroundColor: color }}
            initial={{ width: 0 }}
            animate={{ width: `${clamped * 100}%` }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          />
        )}
        {thresholds.map((t) => (
          <span
            key={t}
            className="absolute inset-y-0 w-px bg-white/40"
            style={{ left: `${t * 100}%` }}
            aria-label={`Threshold ${t}`}
          />
        ))}
      </div>
      {caption !== undefined && <p className="mt-1 text-[10px] text-ink-faint">{caption}</p>}
    </div>
  );
}
