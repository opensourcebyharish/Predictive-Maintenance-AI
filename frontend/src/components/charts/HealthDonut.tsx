import { HeartPulse } from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import type { MachineSummary } from "@/api/types";
import { healthLabel } from "@/lib/format";
import { SERIES } from "@/lib/health";

interface Slice {
  name: string;
  value: number;
  color: string;
}

/**
 * Machine-health distribution donut: healthy / anomalous / elevated /
 * critical / no-data share of the fleet, with a quiet center glyph and a
 * legend that carries absolute counts and shares.
 */
export function HealthDonut({ machines, height = 200 }: { machines: MachineSummary[]; height?: number }) {
  const order = ["healthy", "anomalous", "elevated_risk", "critical_risk", "unknown"] as const;
  const colors: Record<(typeof order)[number], string> = {
    healthy: SERIES.healthy,
    anomalous: SERIES.warning,
    elevated_risk: SERIES.warning,
    critical_risk: SERIES.critical,
    unknown: SERIES.dim,
  };
  const slices: Slice[] = order
    .map((health) => ({
      name: healthLabel(health),
      value: machines.filter((m) => m.health === health).length,
      color: colors[health],
    }))
    .filter((s) => s.value > 0);

  if (machines.length === 0) {
    return <p className="grid h-40 place-items-center text-xs text-ink-faint">No machines ingested yet</p>;
  }

  return (
    <div className="flex items-center gap-5" style={{ minHeight: height }} role="img" aria-label="Machine health distribution">
      <div className="relative shrink-0" style={{ width: 150, height }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={slices}
              dataKey="value"
              nameKey="name"
              innerRadius="64%"
              outerRadius="92%"
              paddingAngle={2}
              cornerRadius={3}
              stroke={SERIES.panel}
              strokeWidth={2}
              isAnimationActive={false}
            >
              {slices.map((slice) => (
                <Cell key={slice.name} fill={slice.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                background: SERIES.panel2,
                border: `1px solid ${SERIES.edgeBright}`,
                borderRadius: 8,
                boxShadow: "0 16px 40px -16px rgb(1 4 9 / 0.95)",
                fontSize: 12,
                padding: "8px 12px",
              }}
              itemStyle={{ color: "#e9eff6", padding: 0 }}
            />
          </PieChart>
        </ResponsiveContainer>
        <span
          className="pointer-events-none absolute inset-0 grid place-items-center text-ink-faint/70"
          aria-hidden="true"
        >
          <HeartPulse className="h-4.5 w-4.5" />
        </span>
      </div>
      <ul className="min-w-0 flex-1 space-y-1.5 text-xs" aria-label="Health legend">
        {slices.map((slice) => {
          const share = Math.round((slice.value / machines.length) * 100);
          return (
            <li key={slice.name} className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: slice.color }} aria-hidden="true" />
              <span className="truncate text-ink-dim">{slice.name}</span>
              <span className="tnum text-ink-faint">{share}%</span>
              <span className="tnum ml-auto pl-3 font-semibold text-ink">{slice.value}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
