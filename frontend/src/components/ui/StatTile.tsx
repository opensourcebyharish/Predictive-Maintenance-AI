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

const NEUTRAL_CHIP = "border-white/10 bg-white/5 text-ink-faint";

/**
 * Big-figure KPI tile: top accent rail (tone-colored), icon chip, muted
 * label, dominant tabular figure, optional hint. Subtle hover elevation.
 */
export function StatTile({ label, value, tone, hint, icon, index = 0, ariaLabel }: StatTileProps) {
  const accent = tone ? healthStyle(tone) : null;
  const chip = accent ? accent.chip : NEUTRAL_CHIP;
  return (
    <motion.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.05, ease: "easeOut" }}
      className="relative overflow-hidden rounded-lg border border-edge bg-panel shadow-panel transition-colors duration-200 hover:border-edge-bright"
      aria-label={ariaLabel}
    >
      {/* Tone rail: a quiet top rule that carries the status color */}
      <span
        aria-hidden="true"
        className={`absolute inset-x-0 top-0 h-0.5 opacity-45 ${accent ? accent.bar : "bg-edge-bright"}`}
      />
      <div className="p-4">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-medium tracking-[0.14em] text-ink-dim uppercase">{label}</span>
          {icon && (
            <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-md border ${chip}`}>{icon}</span>
          )}
        </div>
        <p className={`tnum mt-2.5 text-[28px] font-semibold leading-none tracking-tight ${accent ? accent.text : "text-ink"}`}>
          {typeof value === "number" ? formatCount(value) : value ?? "—"}
        </p>
        {hint !== undefined && <div className="mt-2 text-xs text-ink-faint">{hint}</div>}
      </div>
    </motion.article>
  );
}
