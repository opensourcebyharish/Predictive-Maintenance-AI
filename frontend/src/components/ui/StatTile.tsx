import type { ReactNode } from "react";
import { motion } from "framer-motion";

import { formatCount } from "@/lib/format";
import { healthStyle } from "@/lib/health";

export interface StatTileProps {
  label: string;
  value: number | string | null;
  /** Machine-health tone for the value color (defaults neutral). */
  tone?: string;
  hint?: ReactNode;
  icon?: ReactNode;
  /** Stagger index for the entrance animation. */
  index?: number;
  ariaLabel?: string;
}

/** Big-figure KPI tile with restrained entrance animation. */
export function StatTile({ label, value, tone, hint, icon, index = 0, ariaLabel }: StatTileProps) {
  const accent = tone ? healthStyle(tone) : null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.05, ease: "easeOut" }}
      className="rounded-lg border border-edge bg-panel/80 p-4"
      aria-label={ariaLabel}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium tracking-wide text-ink-dim uppercase">{label}</span>
        {icon && <span className="text-ink-faint">{icon}</span>}
      </div>
      <p className={`tnum mt-2 text-3xl font-semibold leading-none ${accent ? accent.text : "text-ink"}`}>
        {typeof value === "number" ? formatCount(value) : value ?? "—"}
      </p>
      {hint !== undefined && <div className="mt-2 text-xs text-ink-faint">{hint}</div>}
    </motion.div>
  );
}
